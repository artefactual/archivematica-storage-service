"""Tests for the reingest of AIPs through the Storage Service API.

The request phase is exercised on packages stored the way the pipeline stores
them, across the working paths ``start_reingest`` uses: the stored directory
itself for uncompressed AIPs the Storage Service can read directly, an
extracted copy for compressed AIPs, with and without a stored checksum, and a
fetched copy for AIPs in locations it cannot read directly. Requests that
cannot proceed are checked for their responses. Whatever the working path,
the stored AIP itself is never written to.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
import urllib.parse
import uuid
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Protocol

import bagit
import pytest
import requests
from django.conf import settings
from django.test import Client
from metsrw.plugins import premisrw

from archivematica.storage_service.common.compression import COMPRESSION_7Z_BZIP
from archivematica.storage_service.common.compression import Archive
from archivematica.storage_service.common.compression import Archiver
from archivematica.storage_service.common.compression import CompressionError
from archivematica.storage_service.common.compression import override_archiver
from archivematica.storage_service.locations import models
from archivematica.storage_service.locations import reingest
from archivematica.storage_service.locations.models.local_filesystem import (
    LocalFilesystem,
)
from archivematica.storage_service.locations.models.nfs import NFS

PROCESSING_CONFIG = "<processingMCP><preconfiguredChoices/></processingMCP>"

# A preservation derivative is recognised by its ``<name>-<uuid><ext>`` name.
DERIVATIVE_UUID = uuid.uuid4()

# Payload of the built AIPs, relative to ``data/``, laid out as Archivematica
# writes it. It holds something for every selection the reingest types make.
DEFAULT_PAYLOAD: Mapping[str, str] = {
    "objects/hello.txt": "hello\n",
    f"objects/hello-{DERIVATIVE_UUID}.tif": "preservation derivative\n",
    "objects/metadata/metadata.csv": "filename,dc.title\nobjects/hello.txt,Hello\n",
    "objects/submissionDocumentation/transfer-hello/METS.xml": "<mets/>\n",
    "logs/fileFormatIdentification.log": "objects/hello.txt,fmt/111\n",
    "README.html": "<html><body>AIP</body></html>\n",
}


def _age(path: Path, seconds: int = 60) -> None:
    """Move the modification times under ``path`` into the past.

    A reingest merges the updated AIP into the stored directory with rsync,
    whose quick check skips files with the same size and mtime at one-second
    granularity. Stored AIPs are always older than that in practice.
    """
    then = time.time() - seconds
    for entry in [path, *path.rglob("*")]:
        os.utime(entry, (then, then))


def _get_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(
        (Path(root) / name).stat().st_size
        for root, _, names in os.walk(path)
        for name in names
    )


def _compression_event() -> tuple[object, ...]:
    """Return the PREMIS compression event the pipeline sends when storing."""
    return (
        "event",
        premisrw.PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", str(uuid.uuid4())),
        ),
        ("event_type", "compression"),
        ("event_date_time", "2017-08-15T00:30:55"),
        (
            "event_detail",
            (
                "program=7z; "
                "version=p7zip Version 16.02 "
                "(locale=en_US.UTF-8,Utf16=on,HugeFiles=on,2 CPUs); "
                "algorithm=bzip2"
            ),
        ),
        (
            "event_outcome_information",
            (
                "event_outcome_detail",
                (
                    "event_outcome_detail_note",
                    'Standard Output="..."; Standard Error=""',
                ),
            ),
        ),
        (
            "linking_agent_identifier",
            ("linking_agent_identifier_type", "preservation system"),
            ("linking_agent_identifier_value", "Archivematica"),
        ),
    )


def _agent() -> tuple[object, ...]:
    return (
        "agent",
        premisrw.PREMIS_3_0_META,
        (
            "agent_identifier",
            ("agent_identifier_type", "preservation system"),
            ("agent_identifier_value", "Archivematica"),
        ),
        ("agent_name", "Archivematica"),
        ("agent_type", "software"),
    )


class AIPBuilder:
    """Build and store AIPs shaped like the ones Archivematica produces.

    The reingest code paths branch on stored state: compression, stored
    checksum, pointer file and layout. This builder produces valid bags with
    the payload layout Archivematica writes, compresses them with the
    archiver in use and stores them through the API, so that the resulting
    package rows and files look like production ones.
    """

    def __init__(self, client: Client, archiver: Archiver) -> None:
        self.client = client
        self.archiver = archiver

    @staticmethod
    def mets_filename(package_uuid: uuid.UUID) -> str:
        return f"METS.{package_uuid}.xml"

    @staticmethod
    def list_files(directory: Path) -> set[str]:
        """Return the paths of all files under ``directory`` relative to it."""
        return {
            os.path.relpath(os.path.join(root, name), directory)
            for root, _, names in os.walk(directory)
            for name in names
        }

    def build(
        self,
        parent: Path,
        package_uuid: uuid.UUID,
        name: str,
        *,
        payload: Mapping[str, str] = DEFAULT_PAYLOAD,
        mets: str = "<mets/>\n",
    ) -> Path:
        """Write a valid bag named ``name`` under ``parent`` and return its path.

        ``payload`` maps paths relative to the payload directory to their
        content. The METS file is always named after ``package_uuid``. Files
        are written first and the directory is bagged last, so the manifests
        always match the content.
        """
        aip_dir = parent / name
        aip_dir.mkdir(parents=True)
        files = dict(payload)
        files[self.mets_filename(package_uuid)] = mets
        for relative_path, content in files.items():
            path = aip_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        bagit.make_bag(str(aip_dir), checksums=["sha256"])
        return aip_dir

    def compress(self, aip_dir: Path, compression: str = COMPRESSION_7Z_BZIP) -> Path:
        """Compress a bag next to itself."""
        return self.archiver.compress(aip_dir, aip_dir.parent, compression).path

    def store(
        self,
        *,
        package_uuid: uuid.UUID,
        package_path: Path,
        pipeline: models.Pipeline,
        origin_location: models.Location,
        storage_location: models.Location,
    ) -> models.Package:
        """Store the AIP at ``package_path`` through the API, as the pipeline does.

        ``package_path`` is a bag directory or an archive inside
        ``origin_location``. Returns the resulting package.
        """
        compressed = package_path.is_file()
        origin_path = package_path.name if compressed else f"{package_path.name}/"
        response = self.client.post(
            "/api/v2/file/",
            json.dumps(
                {
                    "uuid": str(package_uuid),
                    "origin_location": f"/api/v2/location/{origin_location.uuid}/",
                    "origin_path": origin_path,
                    "current_location": f"/api/v2/location/{storage_location.uuid}/",
                    "current_path": package_path.name,
                    "size": _get_size(package_path),
                    "package_type": models.Package.AIP,
                    "aip_subtype": "Archival Information Package",
                    "origin_pipeline": f"/api/v2/pipeline/{pipeline.uuid}/",
                    "events": [_compression_event()] if compressed else [],
                    "agents": [_agent()],
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
        return models.Package.objects.get(uuid=package_uuid)


@pytest.fixture
def aip_builder(admin_client: Client, fake_archiver: Archiver) -> AIPBuilder:
    """Return a builder that stores AIPs through the API as an administrator.

    The fake archiver stays in use for the test, so no compression tools are
    needed.
    """
    return AIPBuilder(admin_client, fake_archiver)


@dataclass(frozen=True)
class DashboardRequest:
    """A request received by the fake dashboard."""

    method: str
    path: str
    authorization: str | None
    fields: Mapping[str, str]
    """Form fields of a POST request."""


@dataclass(frozen=True)
class ReingestApproval:
    """A reingest approval requested from the fake dashboard."""

    target: str
    """``ingest`` for partial reingest, ``transfer`` for full reingest."""
    name: str
    """Path of the AIP under the pipeline's ``tmp`` directory."""
    package_uuid: uuid.UUID


REINGEST_PATH = re.compile(r"/api/(?P<target>ingest|transfer)/reingest")
PROCESSING_CONFIG_PATH = "/api/processing-configuration/"


def _response(status: int, content_type: str, body: str) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.headers["Content-Type"] = content_type
    result.encoding = "utf-8"
    result._content = body.encode()
    return result


@dataclass
class FakeDashboard:
    """Stand-in for the dashboard API of a pipeline.

    It takes the place of ``requests.request``, the call through which the
    Storage Service reaches a pipeline. It serves the processing
    configurations registered in ``processing_configs``, approves reingest
    requests with ``reingest_uuid`` and records every request it receives.
    """

    url: str = "http://dashboard.test"
    processing_configs: dict[str, str] = field(default_factory=dict)
    reingest_uuid: uuid.UUID = field(default_factory=uuid.uuid4)
    reingest_status: int = 200
    """HTTP status returned to reingest approvals."""
    received: list[DashboardRequest] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        **kwargs: object,
    ) -> requests.Response:
        parts = urllib.parse.urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}" == self.url, url
        self.received.append(
            DashboardRequest(
                method=method,
                path=parts.path,
                authorization=(headers or {}).get("Authorization"),
                fields=dict(data or {}),
            )
        )
        if method == "GET" and parts.path.startswith(PROCESSING_CONFIG_PATH):
            name = parts.path.removeprefix(PROCESSING_CONFIG_PATH)
            config = self.processing_configs.get(name)
            if config is not None:
                return _response(200, "text/xml", config)
        elif method == "POST" and REINGEST_PATH.fullmatch(parts.path):
            if self.reingest_status != 200:
                body = {"error": True, "message": "Approval failed."}
                return _response(
                    self.reingest_status, "application/json", json.dumps(body)
                )
            body = {
                "message": "Approval successful.",
                "reingest_uuid": str(self.reingest_uuid),
            }
            return _response(200, "application/json", json.dumps(body))
        return _response(404, "application/json", json.dumps({"error": True}))

    @property
    def processing_config_requests(self) -> list[str]:
        """Return the names of the processing configurations requested."""
        return [
            request.path.removeprefix(PROCESSING_CONFIG_PATH)
            for request in self.received
            if request.method == "GET"
            and request.path.startswith(PROCESSING_CONFIG_PATH)
        ]

    @property
    def reingest_approvals(self) -> list[ReingestApproval]:
        result = []
        for request in self.received:
            match = REINGEST_PATH.fullmatch(request.path)
            if request.method == "POST" and match:
                result.append(
                    ReingestApproval(
                        target=match.group("target"),
                        name=request.fields["name"],
                        package_uuid=uuid.UUID(request.fields["uuid"]),
                    )
                )
        return result


@pytest.fixture
def dashboard(monkeypatch: pytest.MonkeyPatch) -> FakeDashboard:
    """Put a fake dashboard behind the HTTP client the pipeline model uses."""
    result = FakeDashboard()
    monkeypatch.setattr(requests, "request", result.request)
    return result


@pytest.fixture
def default_space(tmp_path: Path) -> models.Space:
    """Return a space shaped like the default one.

    Its staging path is the Storage Service internal location, as in a
    default deployment.
    """
    space_dir = tmp_path / "space"
    staging_dir = space_dir / "var" / "archivematica" / "storage_service"
    staging_dir.mkdir(parents=True)
    space = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
    )
    LocalFilesystem.objects.create(space=space)
    return space


@pytest.fixture
def internal_location(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=default_space,
        purpose=models.Location.STORAGE_SERVICE_INTERNAL,
        relative_path="var/archivematica/storage_service",
    )


@pytest.fixture
def pipeline(default_space: models.Space, dashboard: FakeDashboard) -> models.Pipeline:
    result = models.Pipeline.objects.create(
        remote_name=dashboard.url,
        api_username="test",
        api_key="test",
    )
    currently_processing = models.Location.objects.create(
        space=default_space,
        purpose=models.Location.CURRENTLY_PROCESSING,
        relative_path="var/archivematica/sharedDirectory",
    )
    Path(currently_processing.full_path).mkdir(parents=True)
    currently_processing.pipeline.add(result)
    return result


@pytest.fixture
def currently_processing(pipeline: models.Pipeline) -> models.Location:
    return models.Location.objects.get(
        pipeline=pipeline, purpose=models.Location.CURRENTLY_PROCESSING
    )


@dataclass(frozen=True)
class Storage:
    """An AIP storage location and whether the service can read it directly."""

    location: models.Location
    remote: bool
    hidden_dir: Path
    """Where the space directory is moved when ``remote``."""


@pytest.fixture
def storage(
    request: pytest.FixtureRequest, tmp_path: Path, pipeline: models.Pipeline
) -> Storage:
    """Return an AIP storage location of the requested kind.

    ``local`` and ``nfs`` are directly readable. ``remote`` is a local space
    that is hidden once a package is stored, so the package has to be fetched
    like one in object storage.
    """
    kind: str = request.param
    space_dir = tmp_path / kind
    staging_dir = tmp_path / f"{kind}_staging"
    space_dir.mkdir()
    staging_dir.mkdir()
    if kind == "nfs":
        space = models.Space.objects.create(
            access_protocol=models.Space.NFS,
            path=str(space_dir),
            staging_path=str(staging_dir),
        )
        NFS.objects.create(
            space=space, remote_name="nfs-server", remote_path="/export", version="nfs4"
        )
    else:
        space = models.Space.objects.create(
            access_protocol=models.Space.LOCAL_FILESYSTEM,
            path=str(space_dir),
            staging_path=str(staging_dir),
        )
        LocalFilesystem.objects.create(space=space)
    location = models.Location.objects.create(
        space=space, purpose=models.Location.AIP_STORAGE, relative_path="aips"
    )
    Path(location.full_path).mkdir()
    location.pipeline.add(pipeline)
    return Storage(
        location=location,
        remote=kind == "remote",
        hidden_dir=tmp_path / f"{kind}_hidden",
    )


def _hide_space(
    space: models.Space, hidden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make a local space unreadable in place, so packages must be fetched.

    The space directory is moved aside and copies out of the space are
    redirected to it, standing in for a remote transport. Directories are
    copied by content, as object storage drivers do.
    """
    space_dir = space.path
    shutil.move(space_dir, hidden_dir)
    original = LocalFilesystem.move_to_storage_service

    def fetch(
        self: LocalFilesystem,
        src_path: str,
        dest_path: str,
        dest_space: models.Space,
    ) -> None:
        if src_path.startswith(space_dir):
            src_path = str(hidden_dir) + src_path[len(space_dir) :]
            if Path(src_path).is_dir():
                src_path = f"{src_path.rstrip('/')}/"
        original(self, src_path, dest_path, dest_space)

    monkeypatch.setattr(LocalFilesystem, "move_to_storage_service", fetch)


@dataclass(frozen=True)
class StoredAIP:
    package: models.Package
    files: frozenset[str]
    """Paths of every file in the bag, relative to the bag directory."""


class StoreAIP(Protocol):
    def __call__(
        self,
        *,
        compressed: bool,
        stored_checksum: bool = True,
        payload: Mapping[str, str] = DEFAULT_PAYLOAD,
    ) -> StoredAIP: ...


@pytest.fixture
def store_aip(
    aip_builder: AIPBuilder,
    tmp_path: Path,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    internal_location: models.Location,
    storage: Storage,
    monkeypatch: pytest.MonkeyPatch,
) -> StoreAIP:
    """Return a callable that builds an AIP and stores it through the API."""
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    def _store(
        *,
        compressed: bool,
        stored_checksum: bool = True,
        payload: Mapping[str, str] = DEFAULT_PAYLOAD,
    ) -> StoredAIP:
        package_uuid = uuid.uuid4()
        bag_dir = aip_builder.build(
            build_dir, package_uuid, f"aip-{package_uuid}", payload=payload
        )
        files = frozenset(aip_builder.list_files(bag_dir))
        artifact = aip_builder.compress(bag_dir) if compressed else bag_dir
        package_path = Path(currently_processing.full_path) / artifact.name
        shutil.move(artifact, package_path)
        package = aip_builder.store(
            package_uuid=package_uuid,
            package_path=package_path,
            pipeline=pipeline,
            origin_location=currently_processing,
            storage_location=storage.location,
        )
        _age(Path(package.full_path))
        if not stored_checksum:
            # Compressed AIPs whose pointer file was generated by the pipeline
            # are stored without a checksum.
            models.Package.objects.filter(uuid=package_uuid).update(checksum=None)
            package.refresh_from_db()
        if storage.remote:
            _hide_space(storage.location.space, storage.hidden_dir, monkeypatch)
        return StoredAIP(package=package, files=files)

    return _store


def _request_reingest(
    client: Client, package: models.Package, data: dict[str, str]
) -> tuple[int, dict[str, object]]:
    response = client.post(
        f"/api/v2/file/{package.uuid}/reingest/",
        json.dumps(data),
        content_type="application/json",
    )
    body: dict[str, object] = json.loads(response.content)
    return response.status_code, body


def _sent_directory(
    approval: ReingestApproval, currently_processing: models.Location
) -> Path:
    """Return the directory the pipeline was told to reingest from."""
    result = Path(currently_processing.full_path) / "tmp" / approval.name
    assert result.is_dir()
    return result


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local", "nfs", "remote"], indirect=True)
@pytest.mark.parametrize(
    ("compressed", "stored_checksum"),
    [(False, True), (True, True), (True, False)],
    ids=["uncompressed", "compressed", "compressed-without-checksum"],
)
@pytest.mark.parametrize(
    ("reingest_type", "target"),
    [
        (models.Package.METADATA_ONLY, "ingest"),
        (models.Package.OBJECTS, "ingest"),
        (models.Package.FULL, "transfer"),
    ],
)
def test_reingest_request_sends_selected_files_and_processing_configuration(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    compressed: bool,
    stored_checksum: bool,
    reingest_type: str,
    target: str,
) -> None:
    stored = store_aip(compressed=compressed, stored_checksum=stored_checksum)
    package = stored.package
    mets = f"data/{aip_builder.mets_filename(package.uuid)}"
    objects = {
        path
        for path in stored.files
        if path.startswith("data/objects/")
        and not path.startswith("data/objects/submissionDocumentation/")
    }
    expected_files = {
        models.Package.METADATA_ONLY: {mets, "data/objects/metadata/metadata.csv"},
        models.Package.OBJECTS: {mets} | objects,
        models.Package.FULL: set(stored.files),
    }[reingest_type] | {"processingMCP.xml"}
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    status_code, body = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": reingest_type,
            "processing_config": "custom",
        },
    )

    assert status_code == 202
    assert body == {
        "error": False,
        "status_code": 202,
        "message": f"Package {package.uuid} sent to pipeline {pipeline} for re-ingest",
        "reingest_uuid": str(dashboard.reingest_uuid),
    }

    # The pipeline is asked for the configuration and then to approve the
    # reingest, with the pipeline's own credentials.
    assert dashboard.processing_config_requests == ["custom"]
    (approval,) = dashboard.reingest_approvals
    assert approval.target == target
    assert approval.package_uuid == package.uuid
    assert {request.authorization for request in dashboard.received} == {
        "ApiKey test:test"
    }

    # The pipeline finds a flat bag under its tmp directory, holding the files
    # selected by the reingest type and the processing configuration.
    sent_dir = _sent_directory(approval, currently_processing)
    assert aip_builder.list_files(sent_dir) == expected_files
    assert (sent_dir / "processingMCP.xml").read_text() == PROCESSING_CONFIG

    package.refresh_from_db()
    assert package.misc_attributes["reingest_pipeline"] == str(pipeline.uuid)


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_with_default_processing_configuration_sends_no_file(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
) -> None:
    package = store_aip(compressed=False).package

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.METADATA_ONLY},
    )

    assert status_code == 202
    assert body["error"] is False
    assert dashboard.processing_config_requests == []
    (approval,) = dashboard.reingest_approvals
    assert aip_builder.list_files(_sent_directory(approval, currently_processing)) == {
        f"data/{aip_builder.mets_filename(package.uuid)}",
        "data/objects/metadata/metadata.csv",
    }


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local", "nfs"], indirect=True)
def test_reingest_request_reads_a_stored_directory_in_place_when_nothing_is_added(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
) -> None:
    """Without a configuration to add, the stored AIP is sent from where it is.

    The pipeline is then given the path of the AIP within its location, as
    it always was, instead of that of a working copy.
    """
    package = store_aip(compressed=False).package

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 202
    (approval,) = dashboard.reingest_approvals
    assert approval.name == f"{package.current_path}/"


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_continues_when_processing_configuration_is_missing(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
) -> None:
    package = store_aip(compressed=False).package

    status_code, body = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.METADATA_ONLY,
            "processing_config": "missing",
        },
    )

    assert status_code == 202
    assert body["error"] is False
    assert dashboard.processing_config_requests == ["missing"]
    (approval,) = dashboard.reingest_approvals
    assert aip_builder.list_files(_sent_directory(approval, currently_processing)) == {
        f"data/{aip_builder.mets_filename(package.uuid)}",
        "data/objects/metadata/metadata.csv",
    }


# Failed requests: the response says why, nothing reaches the pipeline that
# should not, and the AIP stays available for another request.


def _expect_failure(status_code: int, message: str) -> dict[str, object]:
    return {"error": True, "status_code": status_code, "message": message}


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_rejects_unknown_pipelines(
    admin_client: Client, store_aip: StoreAIP, dashboard: FakeDashboard
) -> None:
    package = store_aip(compressed=False).package
    unknown = uuid.uuid4()

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(unknown), "reingest_type": models.Package.FULL},
    )

    assert status_code == 400
    assert body == {
        "error": True,
        "message": f"Pipeline UUID {unknown} failed to return a pipeline",
    }
    assert dashboard.received == []


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_rejects_packages_that_are_not_aips(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
) -> None:
    package = store_aip(compressed=False).package
    models.Package.objects.filter(uuid=package.uuid).update(
        package_type=models.Package.DIP
    )

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 405
    assert body == _expect_failure(405, "Package with type DIP cannot be re-ingested.")
    assert dashboard.received == []
    package.refresh_from_db()
    assert "reingest_pipeline" not in package.misc_attributes


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_rejects_packages_already_being_reingested(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
) -> None:
    package = store_aip(compressed=False).package
    other_pipeline = uuid.uuid4()
    models.Package.objects.filter(uuid=package.uuid).update(
        misc_attributes={"reingest_pipeline": str(other_pipeline)}
    )

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 409
    assert body == _expect_failure(
        409, f"This AIP is already being reingested on {other_pipeline}"
    )
    assert dashboard.received == []
    package.refresh_from_db()
    assert package.misc_attributes["reingest_pipeline"] == str(other_pipeline)


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_fails_when_the_stored_aip_does_not_validate(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
) -> None:
    package = store_aip(compressed=False).package
    aip_dir = Path(package.full_path)
    oxum = bagit.Bag(str(aip_dir)).info["Payload-Oxum"]
    assert isinstance(oxum, str)
    size, count = (int(part) for part in oxum.split("."))
    extra = "corrupted\n"
    with (aip_dir / "data" / "objects" / "hello.txt").open("a") as payload_file:
        payload_file.write(extra)

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 500
    assert body == _expect_failure(
        500,
        "Payload-Oxum validation failed."
        f" Expected {count} files and {size} bytes"
        f" but found {count} files and {size + len(extra)} bytes",
    )
    assert dashboard.received == []
    package.refresh_from_db()
    assert "reingest_pipeline" not in package.misc_attributes


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_fails_without_a_currently_processing_location(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
) -> None:
    package = store_aip(compressed=False).package
    currently_processing.enabled = False
    currently_processing.save()

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 412
    assert body == _expect_failure(
        412,
        f"No currently processing Location is associated with pipeline {pipeline.uuid}",
    )
    assert dashboard.received == []
    package.refresh_from_db()
    assert "reingest_pipeline" not in package.misc_attributes


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_fails_when_the_pipeline_rejects_the_approval(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
) -> None:
    package = store_aip(compressed=False).package
    dashboard.reingest_status = 500

    status_code, body = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.FULL},
    )

    assert status_code == 502
    assert body == _expect_failure(
        502,
        f"Error in approve reingest API. Pipeline {pipeline} returned an"
        " unexpected status code: 500 (Approval failed.)",
    )
    (approval,) = dashboard.reingest_approvals
    assert approval.package_uuid == package.uuid
    package.refresh_from_db()
    assert "reingest_pipeline" not in package.misc_attributes


# Finalization: the pipeline stores the reingested AIP back through a PUT
# with a reingest flag, and the Storage Service merges it into the stored one.

REINGESTED_METS = "<mets>reingested</mets>\n"
REGENERATED_DERIVATIVE_UUID = uuid.uuid4()


def _reingested_payload() -> dict[str, str]:
    """Return the payload of the AIP the pipeline sends back after a reingest.

    Compared with the stored AIP, the metadata changed and grew a file, and
    the preservation derivative was regenerated under a new UUID.
    """
    payload = {
        path: content
        for path, content in DEFAULT_PAYLOAD.items()
        if str(DERIVATIVE_UUID) not in path
    }
    payload[f"objects/hello-{REGENERATED_DERIVATIVE_UUID}.tif"] = "regenerated\n"
    payload["objects/metadata/metadata.csv"] = (
        "filename,dc.title\nobjects/hello.txt,Hello again\n"
    )
    payload["objects/metadata/rights.csv"] = "basis,status\ncopyright,copyrighted\n"
    return payload


def _finish_reingest(
    client: Client,
    package: models.Package,
    *,
    pipeline: models.Pipeline,
    origin_location: models.Location,
    origin_path: str,
    storage_location: models.Location,
    current_path: str,
    size: int,
) -> tuple[int, dict[str, object]]:
    """Store the reingested AIP as the pipeline does at the end of a reingest."""
    response = client.put(
        f"/api/v2/file/{package.uuid}/",
        json.dumps(
            {
                "uuid": str(package.uuid),
                "origin_location": f"/api/v2/location/{origin_location.uuid}/",
                "origin_path": origin_path,
                "current_location": f"/api/v2/location/{storage_location.uuid}/",
                "current_path": current_path,
                "size": size,
                "package_type": models.Package.AIP,
                "aip_subtype": "Archival Information Package",
                "origin_pipeline": f"/api/v2/pipeline/{pipeline.uuid}/",
                "events": [_compression_event()],
                "agents": [_agent()],
                "reingest": True,
            }
        ),
        content_type="application/json",
    )
    body: dict[str, object] = json.loads(response.content) if response.content else {}
    return response.status_code, body


def _stored_root(package: models.Package, storage: Storage) -> Path:
    """Return the path of the stored AIP, behind the stand-in when remote."""
    root = Path(package.full_path)
    if storage.remote:
        root = storage.hidden_dir / root.relative_to(storage.location.space.path)
    return root


def _stored_files(root: Path, archiver: Archiver, scratch: Path) -> dict[str, str]:
    """Return the files of the stored AIP, extracting it first if compressed."""
    aip_dir = archiver.extract(root, scratch) if root.is_file() else root
    return {
        path.relative_to(aip_dir).as_posix(): path.read_text()
        for path in aip_dir.rglob("*")
        if path.is_file()
    }


def _check_fixity(client: Client, package: models.Package) -> dict[str, object]:
    response = client.get(f"/api/v2/file/{package.uuid}/check_fixity/")
    assert response.status_code == 200
    body: dict[str, object] = json.loads(response.content)
    return body


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
@pytest.mark.parametrize(
    "reingest_type", [models.Package.METADATA_ONLY, models.Package.OBJECTS]
)
def test_finish_reingest_merges_the_reingested_aip_into_the_stored_one(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    storage: Storage,
    tmp_path: Path,
    reingest_type: str,
) -> None:
    package = store_aip(compressed=False).package
    before = _stored_files(Path(package.full_path), fake_archiver, tmp_path / "before")
    status_code, _ = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": reingest_type},
    )
    assert status_code == 202
    reingested = aip_builder.build(
        Path(currently_processing.full_path) / "reingested",
        package.uuid,
        f"aip-{package.uuid}",
        payload=_reingested_payload(),
        mets=REINGESTED_METS,
    )

    status_code, _ = _finish_reingest(
        admin_client,
        package,
        pipeline=pipeline,
        origin_location=currently_processing,
        origin_path=f"reingested/{reingested.name}/",
        storage_location=storage.location,
        current_path=reingested.name,
        size=_get_size(reingested),
    )

    assert status_code in {200, 202}
    package = models.Package.objects.get(uuid=package.uuid)
    assert package.status == models.Package.UPLOADED
    assert package.misc_attributes["reingest_pipeline"] is None
    assert package.full_pointer_file_path is None
    after = _stored_files(Path(package.full_path), fake_archiver, tmp_path / "after")
    mets = f"data/METS.{package.uuid}.xml"
    # The METS, the metadata and the derivatives come from the reingested AIP.
    assert after[mets] == REINGESTED_METS
    assert after["data/objects/metadata/metadata.csv"].endswith("Hello again\n")
    assert "data/objects/metadata/rights.csv" in after
    assert f"data/objects/hello-{REGENERATED_DERIVATIVE_UUID}.tif" in after
    assert f"data/objects/hello-{DERIVATIVE_UUID}.tif" not in after
    # The originals and the logs are the stored AIP's own.
    assert after["data/objects/hello.txt"] == before["data/objects/hello.txt"]
    assert (
        after["data/logs/fileFormatIdentification.log"]
        == before["data/logs/fileFormatIdentification.log"]
    )
    fixity = _check_fixity(admin_client, package)
    assert fixity["success"] is True, fixity


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
@pytest.mark.parametrize(
    ("stored_compressed", "reingested_compressed"),
    [(False, True), (True, False), (True, True)],
    ids=[
        "uncompressed-to-compressed",
        "compressed-to-uncompressed",
        "compressed-to-compressed",
    ],
)
def test_finish_reingest_applies_the_compression_of_the_reingested_aip(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    storage: Storage,
    tmp_path: Path,
    stored_compressed: bool,
    reingested_compressed: bool,
) -> None:
    package = store_aip(compressed=stored_compressed).package
    stored_path = Path(package.full_path)
    status_code, _ = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.METADATA_ONLY},
    )
    assert status_code == 202
    reingested = aip_builder.build(
        Path(currently_processing.full_path) / "reingested",
        package.uuid,
        f"aip-{package.uuid}",
        payload=_reingested_payload(),
        mets=REINGESTED_METS,
    )
    if reingested_compressed:
        reingested = aip_builder.compress(reingested)

    status_code, _ = _finish_reingest(
        admin_client,
        package,
        pipeline=pipeline,
        origin_location=currently_processing,
        origin_path=f"reingested/{reingested.name}{'' if reingested_compressed else '/'}",
        storage_location=storage.location,
        current_path=reingested.name,
        size=_get_size(reingested),
    )

    assert status_code in {200, 202}
    package = models.Package.objects.get(uuid=package.uuid)
    assert package.status == models.Package.UPLOADED
    assert Path(package.full_path).name == reingested.name
    assert Path(package.full_path).is_file() is reingested_compressed
    if Path(package.full_path) != stored_path:
        assert not stored_path.exists()
    if reingested_compressed:
        assert package.full_pointer_file_path
        assert Path(package.full_pointer_file_path).is_file()
    else:
        assert package.full_pointer_file_path is None
    after = _stored_files(Path(package.full_path), fake_archiver, tmp_path / "after")
    assert after[f"data/METS.{package.uuid}.xml"] == REINGESTED_METS
    assert f"data/objects/hello-{REGENERATED_DERIVATIVE_UUID}.tif" in after
    fixity = _check_fixity(admin_client, package)
    assert fixity["success"] is True, fixity


# The request phase reads the stored AIP and adds the processing configuration
# to what it sends, on a working copy. Uncompressed AIPs in storage the Storage
# Service reads directly used to be written to in place.

# Every storage and package form.
STORED_AIPS = [
    pytest.param("local", False, id="local-uncompressed"),
    pytest.param("nfs", False, id="nfs-uncompressed"),
    pytest.param("remote", False, id="remote-uncompressed"),
    pytest.param("local", True, id="local-compressed"),
    pytest.param("nfs", True, id="nfs-compressed"),
    pytest.param("remote", True, id="remote-compressed"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("storage", "compressed"), STORED_AIPS, indirect=["storage"])
@pytest.mark.parametrize(
    "reingest_type",
    [models.Package.METADATA_ONLY, models.Package.OBJECTS, models.Package.FULL],
)
def test_reingest_request_leaves_the_stored_aip_unchanged(
    admin_client: Client,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    storage: Storage,
    tmp_path: Path,
    compressed: bool,
    reingest_type: str,
) -> None:
    package = store_aip(compressed=compressed).package
    root = _stored_root(package, storage)
    before = _stored_files(root, fake_archiver, tmp_path / "before")
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": reingest_type,
            "processing_config": "custom",
        },
    )

    assert status_code == 202
    assert _stored_files(root, fake_archiver, tmp_path / "after") == before


@pytest.mark.django_db
@pytest.mark.parametrize(("storage", "compressed"), STORED_AIPS, indirect=["storage"])
def test_rejected_reingest_request_leaves_the_stored_aip_unchanged(
    admin_client: Client,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    storage: Storage,
    tmp_path: Path,
    compressed: bool,
) -> None:
    """The pipeline rejects the approval after the configuration was fetched."""
    package = store_aip(compressed=compressed).package
    root = _stored_root(package, storage)
    before = _stored_files(root, fake_archiver, tmp_path / "before")
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG
    dashboard.reingest_status = 500

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.METADATA_ONLY,
            "processing_config": "custom",
        },
    )

    assert status_code == 502
    assert _stored_files(root, fake_archiver, tmp_path / "after") == before


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local", "nfs"], indirect=True)
@pytest.mark.parametrize(
    "reingest_type", [models.Package.METADATA_ONLY, models.Package.OBJECTS]
)
def test_finish_reingest_leaves_no_processing_configuration_in_the_stored_aip(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    storage: Storage,
    tmp_path: Path,
    reingest_type: str,
) -> None:
    """A partial reingest is finalized on top of the stored AIP."""
    package = store_aip(compressed=False).package
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG
    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": reingest_type,
            "processing_config": "custom",
        },
    )
    assert status_code == 202
    reingested = aip_builder.build(
        Path(currently_processing.full_path) / "reingested",
        package.uuid,
        f"aip-{package.uuid}",
        payload=_reingested_payload(),
        mets=REINGESTED_METS,
    )

    status_code, _ = _finish_reingest(
        admin_client,
        package,
        pipeline=pipeline,
        origin_location=currently_processing,
        origin_path=f"reingested/{reingested.name}/",
        storage_location=storage.location,
        current_path=reingested.name,
        size=_get_size(reingested),
    )

    assert status_code in {200, 202}
    package = models.Package.objects.get(uuid=package.uuid)
    after = _stored_files(Path(package.full_path), fake_archiver, tmp_path / "after")
    assert "processingMCP.xml" not in after


@pytest.mark.django_db
@pytest.mark.parametrize(("storage", "compressed"), STORED_AIPS, indirect=["storage"])
@pytest.mark.parametrize("accepted", [True, False], ids=["accepted", "rejected"])
def test_reingest_request_leaves_no_working_copy_behind(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    internal_location: models.Location,
    compressed: bool,
    accepted: bool,
) -> None:
    package = store_aip(compressed=compressed).package
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG
    if not accepted:
        dashboard.reingest_status = 500

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.FULL,
            "processing_config": "custom",
        },
    )

    assert status_code == (202 if accepted else 502)
    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


def _make_read_only(root: Path) -> None:
    """Remove the write permission from everything under ``root``."""
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def _writable_entries(root: Path) -> dict[str, bool]:
    """Map every path under ``root`` to whether its owner may write it."""
    return {
        path.relative_to(root).as_posix(): bool(path.stat().st_mode & stat.S_IWUSR)
        for path in root.rglob("*")
    }


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_delivers_a_writable_copy_of_a_read_only_aip(
    admin_client: Client,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    internal_location: models.Location,
    storage: Storage,
    tmp_path: Path,
) -> None:
    """Stored AIPs may be read-only; what the pipeline receives must not be."""
    package = store_aip(compressed=False).package
    root = _stored_root(package, storage)
    _make_read_only(root)
    before = _stored_files(root, fake_archiver, tmp_path / "before")
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.FULL,
            "processing_config": "custom",
        },
    )

    assert status_code == 202
    (approval,) = dashboard.reingest_approvals
    sent_dir = _sent_directory(approval, currently_processing)
    writable = _writable_entries(sent_dir)
    assert all(writable.values()), [path for path, ok in writable.items() if not ok]
    assert _stored_files(root, fake_archiver, tmp_path / "after") == before
    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_discards_the_working_copy_of_a_read_only_aip(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    default_space: models.Space,
    internal_location: models.Location,
    storage: Storage,
    tmp_path: Path,
) -> None:
    """When the delivery copies rather than moves, the copy must be removable."""
    package = store_aip(compressed=False).package
    _make_read_only(_stored_root(package, storage))
    # The pipeline space stages elsewhere, so the delivery leaves the working
    # copy in the internal location for the request to discard.
    staging_dir = tmp_path / "pipeline_staging"
    staging_dir.mkdir()
    default_space.staging_path = str(staging_dir)
    default_space.save()
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.METADATA_ONLY,
            "processing_config": "custom",
        },
    )

    assert status_code == 202
    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_discards_a_working_copy_it_could_not_complete(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    internal_location: models.Location,
) -> None:
    """A failure while copying must not leave the partial copy behind.

    An AIP without a metadata directory makes the copy of a metadata-only
    selection fail, as the delivery itself used to.
    """
    payload = {
        path: content
        for path, content in DEFAULT_PAYLOAD.items()
        if not path.startswith("objects/metadata/")
    }
    package = store_aip(compressed=False, payload=payload).package
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    with pytest.raises(models.StorageException):
        _request_reingest(
            admin_client,
            package,
            {
                "pipeline": str(pipeline.uuid),
                "reingest_type": models.Package.METADATA_ONLY,
                "processing_config": "custom",
            },
        )

    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


@pytest.mark.django_db
def test_writable_copy_is_removed_when_it_fails_after_a_read_only_directory(
    aip_builder: AIPBuilder, internal_location: models.Location, tmp_path: Path
) -> None:
    """The partial copy must be removable whatever was copied before the failure."""
    bag_dir = aip_builder.build(tmp_path / "source", uuid.uuid4(), "aip")
    (bag_dir / "data" / "objects" / "metadata").chmod(0o555)
    source = reingest.WorkingCopy(
        path=f"{bag_dir}/", location=internal_location, disposable=False
    )

    with pytest.raises(models.StorageException):
        reingest._writable_copy(source, ["data/objects/metadata/", "data/missing"])

    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


@pytest.mark.django_db
def test_writable_copy_fails_when_a_directory_cannot_be_read(
    aip_builder: AIPBuilder, internal_location: models.Location, tmp_path: Path
) -> None:
    """An unreadable directory must abort the copy rather than be left out."""
    if os.geteuid() == 0:
        pytest.skip("permissions are not enforced for root")
    bag_dir = aip_builder.build(tmp_path / "source", uuid.uuid4(), "aip")
    unreadable = bag_dir / "data" / "objects" / "metadata"
    unreadable.chmod(0o000)
    source = reingest.WorkingCopy(
        path=f"{bag_dir}/", location=internal_location, disposable=False
    )

    try:
        with pytest.raises(models.StorageException):
            reingest._writable_copy(source, ["data/objects/"])
    finally:
        unreadable.chmod(0o755)

    working_copies = [
        name
        for name in os.listdir(internal_location.full_path)
        if name.startswith("tmp")
    ]
    assert working_copies == []


@pytest.fixture
def recorded_rsync_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[], list[list[str]]]:
    """Put an rsync on the path that records its arguments before running the real one."""
    real_rsync = shutil.which("rsync")
    assert real_rsync
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "rsync.log"
    tool = bin_dir / "rsync"
    tool.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexec "{real_rsync}" "$@"\n'
    )
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def commands() -> list[list[str]]:
        if not log.exists():
            return []
        return [line.split() for line in log.read_text().splitlines()]

    return commands


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
def test_reingest_request_copies_the_stored_aip_with_the_bounded_rsync_transfer(
    admin_client: Client,
    store_aip: StoreAIP,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    internal_location: models.Location,
    storage: Storage,
    recorded_rsync_commands: Callable[[], list[list[str]]],
) -> None:
    """The working copy goes through the same bounded transfer as every other move.

    Copying in process would hold the request worker for as long as the
    copy takes; rsync runs as a subprocess with the idle and runtime limits
    the service applies everywhere.
    """
    package = store_aip(compressed=False).package
    stored = _stored_root(package, storage)
    dashboard.processing_configs["custom"] = PROCESSING_CONFIG

    status_code, _ = _request_reingest(
        admin_client,
        package,
        {
            "pipeline": str(pipeline.uuid),
            "reingest_type": models.Package.FULL,
            "processing_config": "custom",
        },
    )

    assert status_code == 202
    copies = [
        command
        for command in recorded_rsync_commands()
        if command[-2].startswith(str(stored))
        and command[-1].startswith(internal_location.full_path)
    ]
    assert copies, recorded_rsync_commands()
    for command in copies:
        assert f"--timeout={settings.RSYNC_IO_TIMEOUT_SECONDS}" in command
        assert "--chmod=Fug+rw,o-rwx,Dug+rwx,o-rwx" in command


class _ArchiverFailingAt:
    """Wrap an archiver so that one of its operations fails, as a tool would."""

    def __init__(self, inner: Archiver, operation: str) -> None:
        self.inner = inner
        self.operation = operation

    def compress(
        self, source: Path, destination_dir: Path, compression: str
    ) -> Archive:
        if self.operation == "compress":
            raise CompressionError("the tool failed")
        return self.inner.compress(source, destination_dir, compression)

    def extract(
        self,
        archive: Path,
        destination_dir: Path,
        compression: str | None = None,
        member: str | None = None,
    ) -> Path:
        if self.operation == "extract":
            raise CompressionError("the tool failed")
        return self.inner.extract(archive, destination_dir, compression, member)

    def root_directory(self, archive: Path) -> str:
        return self.inner.root_directory(archive)


@pytest.mark.django_db
@pytest.mark.parametrize("storage", ["local"], indirect=True)
@pytest.mark.parametrize(
    ("failing", "left_in_internal_location"),
    [("extract", "archive"), ("compress", "directory")],
    ids=["extraction", "compression"],
)
def test_finish_reingest_failure_leaves_the_stored_aip_alone(
    admin_client: Client,
    aip_builder: AIPBuilder,
    store_aip: StoreAIP,
    fake_archiver: Archiver,
    dashboard: FakeDashboard,
    pipeline: models.Pipeline,
    currently_processing: models.Location,
    internal_location: models.Location,
    storage: Storage,
    tmp_path: Path,
    failing: str,
    left_in_internal_location: str,
) -> None:
    """A tool failure during finalization stops it without touching storage.

    The reingested AIP has already left the pipeline by then: it stays in
    the internal location, as the archive when it could not be extracted or
    as the extracted directory when it could not be compressed, for an
    operator to recover. The package is no longer marked as reingesting.
    """
    package = store_aip(compressed=False).package
    before = _stored_files(Path(package.full_path), fake_archiver, tmp_path / "before")
    status_code, _ = _request_reingest(
        admin_client,
        package,
        {"pipeline": str(pipeline.uuid), "reingest_type": models.Package.METADATA_ONLY},
    )
    assert status_code == 202
    reingested = aip_builder.build(
        Path(currently_processing.full_path) / "reingested",
        package.uuid,
        f"aip-{package.uuid}",
        payload=_reingested_payload(),
        mets=REINGESTED_METS,
    )
    archive = aip_builder.compress(reingested)

    with (
        override_archiver(_ArchiverFailingAt(fake_archiver, failing)),
        pytest.raises(models.StorageException),
    ):
        _finish_reingest(
            admin_client,
            package,
            pipeline=pipeline,
            origin_location=currently_processing,
            origin_path=f"reingested/{archive.name}",
            storage_location=storage.location,
            current_path=archive.name,
            size=_get_size(archive),
        )

    package.refresh_from_db()
    assert package.status == models.Package.UPLOADED
    assert package.misc_attributes["reingest_pipeline"] is None
    assert (
        _stored_files(Path(package.full_path), fake_archiver, tmp_path / "after")
        == before
    )
    internal = Path(internal_location.full_path)
    if left_in_internal_location == "archive":
        assert (internal / archive.name).is_file()
    else:
        assert (internal / reingested.name).is_dir()
