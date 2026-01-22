"""Integration testing.

This module tests Archivematica Storage Service in isolation. It does not
require Archivematica pipelines deployed.

Currently, the tests in this module are executed via Docker Compose. It may be
worth investigating a setup where pytest orchestrates Compose services instead.

Missing: encryption, multiple replicators, packages generated with older versions
of Archivematica, etc...
"""

import base64
import json
import os
import re
import shutil
import tarfile
import tempfile
import uuid
from collections.abc import Iterable
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from typing import Protocol
from typing import TypedDict
from typing import cast

import boto3
import gnupg
import pytest
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError
from django.contrib import messages
from django.http import StreamingHttpResponse
from django.test import Client as DjangoTestClient
from django.urls import reverse
from metsrw.plugins import premisrw
from pytest_django.fixtures import SettingsWrapper

from archivematica.storage_service.common import gpgutils
from archivematica.storage_service.common import utils
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations.models import Event
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models import Pipeline
from archivematica.storage_service.locations.models import Space

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)

TagName = str
Attribute = str
Value = str
Element = tuple[Attribute, Value]

PremisAgent = tuple[
    TagName,
    dict[str, str],
    tuple[TagName, Element, Element],
    Element,
    Element,
]

PremisEvent = tuple[
    TagName,
    dict[str, str],
    tuple[TagName, Element, Element],
    Element,
    Element,
    Element,
    tuple[TagName, tuple[TagName, Element]],
    tuple[TagName, Element, Element],
]


class LocationResponseResult(TypedDict):
    description: str | None
    enabled: bool
    path: str
    pipeline: list[str]
    purpose: str
    quota: int | None
    relative_path: str
    resource_uri: str
    space: str
    used: int
    uuid: str


FIXTURES_DIR = Path(__file__).parent / "fixtures"

COMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513054116-5658e603-277b-4292-9b58-20bf261c8f88.7z"
)
UNCOMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513060703-828c44bb-e631-4137-8638-bda4434218dc"
)


class HttpResponse(Protocol):
    status_code: int
    content: bytes

    @property
    def text(self) -> str: ...


class Client:
    """Slim API client."""

    def __init__(self, admin_client: DjangoTestClient) -> None:
        self.admin_client = admin_client

    def add_space(self, data: dict[str, str | bool]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/space/", json.dumps(data), content_type="application/json"
        )

    def add_pipeline(self, data: dict[str, str | bool]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/pipeline/", json.dumps(data), content_type="application/json"
        )

    def get_pipelines(self, data: dict[str, str]) -> HttpResponse:
        return self.admin_client.get("/api/v2/pipeline/", data)

    def add_location(self, data: dict[str, str | list[str]]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/location/", json.dumps(data), content_type="application/json"
        )

    def set_location(
        self, location_id: uuid.UUID, data: dict[str, str | list[dict[str, str]]]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/location/{location_id}/",
            json.dumps(data),
            content_type="application/json",
        )

    def get_locations(self, data: dict[str, str]) -> HttpResponse:
        return self.admin_client.get("/api/v2/location/", data)

    def browse_location(
        self, location_id: uuid.UUID, data: dict[str, str]
    ) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/location/{location_id}/browse/", data)

    def add_file(
        self,
        file_id: uuid.UUID,
        data: dict[str, str | int | list[PremisEvent] | list[PremisAgent]],
    ) -> HttpResponse:
        return self.admin_client.put(
            f"/api/v2/file/{file_id}/",
            json.dumps(data),
            content_type="application/json",
        )

    def get_files(self) -> HttpResponse:
        return self.admin_client.get("/api/v2/file/")

    def get_pointer_file(self, file_id: uuid.UUID) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/pointer_file/")

    def check_fixity(self, file_id: uuid.UUID) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/check_fixity/")

    def request_aip_recovery(
        self, file_id: uuid.UUID, data: dict[str, str | int]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/file/{file_id}/recover_aip/",
            json.dumps(data),
            content_type="application/json",
        )

    def approve_aip_recovery_request(self, event_id: int) -> HttpResponse:
        # Not possible via API.
        return self.admin_client.post(
            reverse("locations:aip_recover_request"),
            {
                "event_id": event_id,
                "decision": package_request.PackageRequestDecision.APPROVE.value,
                "status_reason": "Approved!",
            },
            follow=True,
        )

    def request_aip_deletion(
        self, file_id: uuid.UUID, data: dict[str, str | int]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/file/{file_id}/delete_aip/",
            json.dumps(data),
            content_type="application/json",
        )

    def request_reingest(
        self, file_id: uuid.UUID, data: dict[str, str]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/file/{file_id}/reingest/",
            json.dumps(data),
            content_type="application/json",
        )

    def review_aip_deletion(
        self, file_id: uuid.UUID, data: dict[str, str | int]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/file/{file_id}/review_aip_deletion/",
            json.dumps(data),
            content_type="application/json",
        )

    def download_file(self, file_id: uuid.UUID) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/download/")


@pytest.fixture(scope="session")
def client(admin_client: DjangoTestClient) -> Client:
    return Client(admin_client)


@pytest.fixture
def working_directory_path(tmp_path: Path) -> Path:
    result = tmp_path / "work"
    result.mkdir()

    # Similar to the internalDirs created in the Dockerfile.
    (result / "home" / "archivematica").mkdir(parents=True)
    (result / "var" / "archivematica" / "storage_service").mkdir(parents=True)
    (result / "var" / "archivematica" / "sharedDirectory").mkdir(parents=True)

    return result


@pytest.fixture(scope="function")
def startup(working_directory_path: Path) -> None:
    """Create default space and its locations.

    Storage Service provisions a default space and a number of locations when
    the application starts. Its purpose is questionable but this module is just
    trying to reproduce it.

        * space (staging_path=/var/archivematica/storage_service, path=/)
        * location (purpose=TRANSFER_SOURCE, path=home)
        * location (purpose=AIP_STORAGE, path=/var/archivematica/sharedDirectory/www/AIPsStore)
        * location (purpose=DIP_STORAGE, path=/var/archivematica/sharedDirectory/www/DIPsStore)
        * location (purpose=BACKLOG, path=/var/archivematica/sharedDirectory/www/AIPsStore/transferBacklog)
        * location (purpose=STORAGE_SERVICE_INTERNAL, path=/var/archivematica/storage_service)
        * location (purpose=AIP_RECOVERY, path=/var/archivematica/storage_service/recover)

    From the list above, CURRENTLY_PROCESSING is missing but that's later added
    when a pipeline is registered.
    """
    from archivematica.storage_service.common.startup import startup

    startup(working_directory_path, start_async=False)  # TODO: get rid of this!


def get_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    size = 0
    for dirpath, _, filenames in os.walk(path):
        directory = Path(dirpath)
        for filename in filenames:
            size += (directory / filename).stat().st_size
    return size


class StorageScenario:
    """Storage test scenario."""

    PIPELINE_UUID = uuid.UUID("00000b87-1655-4b7e-bbf8-344b317da334")
    PACKAGE_UUID = uuid.UUID("5658e603-277b-4292-9b58-20bf261c8f88")
    OBJECT_STORAGE_PROTOCOLS = {Space.S3, Space.RCLONE}

    SPACES: dict[str, dict[str, str | bool]] = {
        Space.S3: {
            "access_protocol": Space.S3,
            "path": "",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/s3_staging_path",
            "endpoint_url": "http://minio:9000",
            "access_key_id": "minio",
            "secret_access_key": "minio123",
            "region": "planet-earth",
            "bucket": "aip-storage",
        },
        Space.RCLONE: {
            "access_protocol": Space.RCLONE,
            "path": "",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/rclone_staging_path",
            "remote_name": "mys3",
            "container": "mybucket",
        },
        Space.NFS: {
            "access_protocol": Space.NFS,
            "path": "/var/archivematica/sharedDirectory/tmp/nfs_mount",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/nfs_staging_path",
            "manually_mounted": False,
            "remote_name": "nfs-server",
            "remote_path": "???",
            "version": "nfs4",
        },
        Space.LOCAL_FILESYSTEM: {
            "access_protocol": Space.LOCAL_FILESYSTEM,
            "path": "/var/archivematica/sharedDirectory/tmp/local_fs",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/local_fs_staging_path",
        },
    }

    def __init__(
        self,
        *,
        storage_protocol: str,
        replication_protocol: str = "",
        pkg: Path,
        compressed: bool,
    ) -> None:
        self.storage_protocol = storage_protocol
        self.aip_storage_location_attrs: LocationResponseResult | None = None
        self.replication_protocol = replication_protocol
        self.pkg = pkg
        self.pkg_name = (
            f"foobar-{self.PACKAGE_UUID}{''.join(pkg.suffixes) if compressed else ''}"
        )
        self.compressed = compressed
        self._object_storage_bucket_name: str | None = None

    def init(
        self,
        admin_client: DjangoTestClient,
        working_directory_path: Path,
        *,
        s3_bucket: str | None = None,
    ) -> None:
        self.client = Client(admin_client)
        self.shared_directory_path = (
            working_directory_path / "var" / "archivematica" / "sharedDirectory"
        )
        if s3_bucket is not None:
            self._object_storage_bucket_name = s3_bucket
        self.register_pipeline()
        self.register_aip_storage_location()
        if self.replication_protocol:
            self.register_aip_storage_replicator()
        self.copy_fixture(self.shared_directory_path)

    def register_pipeline(self) -> None:
        resp = self.client.add_pipeline(
            {
                "uuid": str(self.PIPELINE_UUID),
                "description": "Beefy pipeline",
                "create_default_locations": True,
                "shared_path": str(self.shared_directory_path),
                "remote_name": "http://127.0.0.1:65534",
                "api_username": "test",
                "api_key": "test",
            }
        )
        assert resp.status_code == 201

    def _adjust_space_data(self, data: dict[str, str | bool]) -> dict[str, str | bool]:
        adjusted = data.copy()
        for attr in ["path", "staging_path"]:
            value = adjusted.get(attr)
            if isinstance(value, str) and value.startswith(
                "/var/archivematica/sharedDirectory"
            ):
                adjusted[attr] = value.replace(
                    "/var/archivematica/sharedDirectory",
                    str(self.shared_directory_path),
                )
        return adjusted

    def register_aip_storage_location(self) -> None:
        """Register AIP Storage location."""

        # Add space.
        resp = self.client.add_space(self._space_definition(self.storage_protocol))
        assert resp.status_code == 201
        space = json.loads(resp.text)

        # Add location.
        resp = self.client.add_location(
            {
                "relative_path": "aips",
                "staging_path": "",
                "purpose": Location.AIP_STORAGE,
                "space": space["resource_uri"],
                "pipeline": [f"/api/v2/pipeline/{self.PIPELINE_UUID}/"],
            }
        )
        assert resp.status_code == 201
        self.aip_storage_location_attrs = json.loads(resp.text)

    def get_compression_event(self) -> PremisEvent:
        return (
            "event",
            premisrw.PREMIS_META,
            (
                "event_identifier",
                ("event_identifier_type", "UUID"),
                ("event_identifier_value", "4711f4eb-8903-4e58-85da-4827e6530d0b"),
            ),
            ("event_type", "compression"),
            ("event_date_time", "2017-08-15T00:30:55"),
            (
                "event_detail",
                (
                    "program=7z; "
                    "version=p7zip Version 9.20 "
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
                ("linking_agent_identifier_type", "foobar"),
                ("linking_agent_identifier_value", "foobar"),
            ),
        )

    def get_agent(self) -> PremisAgent:
        return (
            "agent",
            premisrw.PREMIS_3_0_META,
            (
                "agent_identifier",
                ("agent_identifier_type", "foobar"),
                ("agent_identifier_value", "foobar"),
            ),
            ("agent_name", "foobar"),
            ("agent_type", "foobar"),
        )

    def register_aip_storage_replicator(self) -> None:
        """Register AIP Storage replicator."""

        # 1. Add space.
        resp = self.client.add_space(self._space_definition(self.replication_protocol))
        assert resp.status_code == 201
        space = json.loads(resp.text)

        # 2. Add replicator location.
        resp = self.client.add_location(
            {
                "relative_path": "aips",
                "staging_path": "",
                "purpose": Location.REPLICATOR,
                "space": space["resource_uri"],
                "pipeline": [f"/api/v2/pipeline/{self.PIPELINE_UUID}/"],
            }
        )
        assert resp.status_code == 201
        rp_location = json.loads(resp.text)

        # 3. Install replicator (not possible via API).
        rp_location = Location.objects.get(uuid=rp_location["uuid"])
        assert self.aip_storage_location_attrs is not None
        as_location = Location.objects.get(uuid=self.aip_storage_location_attrs["uuid"])
        as_location.replicators.add(rp_location)
        assert (
            Location.objects.get(uuid=as_location.uuid).replicators.all().count() == 1
        )

    def copy_fixture(self, target_path: Path) -> None:
        dst = target_path / self.pkg_name
        if self.pkg.is_dir():
            if not dst.exists():
                shutil.copytree(FIXTURES_DIR / self.pkg, dst)
            assert dst.is_dir()
        else:
            shutil.copy(FIXTURES_DIR / self.pkg, dst)
            assert dst.is_file()

    def store_aip(self) -> None:
        resp = self.client.get_locations(
            {
                "pipeline_uuid": str(self.PIPELINE_UUID),
                "purpose": Location.CURRENTLY_PROCESSING,
            }
        )
        cp_location = json.loads(resp.text)["objects"][0]

        assert self.aip_storage_location_attrs is not None
        as_location = self.aip_storage_location_attrs

        aip_id = self.PACKAGE_UUID.hex
        aip_id_chunks = [aip_id[i : i + 4] for i in range(0, len(aip_id), 4)]

        resp = self.client.add_file(
            self.PACKAGE_UUID,
            {
                "uuid": str(self.PACKAGE_UUID),
                "origin_location": cp_location["resource_uri"],
                "origin_path": f"{self.pkg_name}{'/' if not self.compressed else ''}",
                "current_location": as_location["resource_uri"],
                "current_path": self.pkg_name,
                "size": get_size(self.pkg),
                "package_type": Package.AIP,
                "aip_subtype": "Archival Information Package",
                "origin_pipeline": f"/api/v2/pipeline/{self.PIPELINE_UUID}/",
                "events": [self.get_compression_event()],
                "agents": [self.get_agent()],
            },
        )
        assert resp.status_code == 201

        aip = json.loads(resp.text)
        aip_path_parts = [as_location["path"], *aip_id_chunks, self.pkg_name]
        aip_path = Path(*aip_path_parts)
        assert aip["uuid"] == str(self.PACKAGE_UUID)
        assert aip["current_full_path"] == str(aip_path)
        if self.storage_protocol in self.OBJECT_STORAGE_PROTOCOLS:
            stored_size = Package.objects.get(uuid=self.PACKAGE_UUID).size
            assert stored_size == get_size(self.pkg)
        else:
            assert get_size(aip_path) > 1

    def _space_definition(self, protocol: str) -> dict[str, str | bool]:
        data = self._adjust_space_data(self.SPACES[protocol])
        bucket_key = self._object_storage_bucket_key(protocol)
        if bucket_key:
            bucket_name = self._object_storage_bucket_name
            if not bucket_name:
                raise RuntimeError(
                    "Object storage spaces require the s3_browse_bucket fixture to be "
                    "passed into StorageScenario.init()."
                )
            data[bucket_key] = bucket_name
        return data

    def _object_storage_bucket_key(self, protocol: str) -> str:
        if protocol == Space.S3:
            return "bucket"
        if protocol == Space.RCLONE:
            return "container"
        return ""

    def assert_stored(self) -> None:
        if self.replication_protocol:
            # We have two packages, the original and a replica.
            expected_files_count = 2
        else:
            expected_files_count = 1

        resp = self.client.get_files()
        files = json.loads(resp.text)
        assert files["meta"]["total_count"] == expected_files_count
        assert len(files["objects"]) == expected_files_count

        # Fixity checks.
        resp = self.client.check_fixity(files["objects"][0]["uuid"])
        assert resp.status_code == 200
        assert json.loads(resp.text)["success"] is True

        if self.replication_protocol:
            resp = self.client.check_fixity(files["objects"][1]["uuid"])
            assert resp.status_code == 200
            assert json.loads(resp.text)["success"] is True

        # We have a pointer file (not for uncompressed AIPs yet).
        if self.compressed:
            resp = self.client.get_pointer_file(self.PACKAGE_UUID)
            assert resp.status_code == 200


@pytest.mark.parametrize(
    "storage_scenario",
    [
        StorageScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.NFS,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.NFS,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.NFS,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.NFS,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        StorageScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
    ],
    ids=[
        "nfs_to_s3_compressed",
        "nfs_to_s3_uncompressed",
        "nfs_to_rclone_compressed",
        "nfs_to_rclone_uncompressed",
        "s3_to_nfs_compressed",
        "s3_to_nfs_uncompressed",
        "rclone_to_nfs_compressed",
        "rclone_to_nfs_uncompressed",
        "s3_to_s3_compressed",
        "s3_to_s3_uncompressed",
        "rclone_to_rclone_compressed",
        "rclone_to_rclone_uncompressed",
        "local_fs_to_s3_compressed",
        "local_fs_to_s3_uncompressed",
        "local_fs_to_rclone_compressed",
        "local_fs_to_rclone_uncompressed",
        "s3_to_local_fs_compressed",
        "s3_to_local_fs_uncompressed",
        "rclone_to_local_fs_compressed",
        "rclone_to_local_fs_uncompressed",
    ],
)
@pytest.mark.django_db
def test_main(
    startup: None,
    storage_scenario: StorageScenario,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
) -> None:
    storage_scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    storage_scenario.store_aip()
    storage_scenario.assert_stored()


class AIPRecoveryScenario(StorageScenario):
    def corrupt_package(self) -> None:
        # This will not work with remote spaces (S3, RClone, etc).
        package = Package.objects.get(uuid=self.PACKAGE_UUID)
        package_path = Path(package.full_path)
        if self.compressed:
            package_path.unlink()
            package_path.touch()
        else:
            # The tagmanifest files are used in utils.generate_checksum.
            for p in package_path.glob("**/tagmanifest*.txt"):
                p.unlink()
                p.touch()
        package.save()

        resp = self.client.check_fixity(self.PACKAGE_UUID)
        assert resp.status_code == 200
        assert not json.loads(resp.text)["success"]

    def copy_fixture_to_aip_recovery_location(self) -> None:
        resp = self.client.get_locations(
            {"pipeline_uuid": str(self.PIPELINE_UUID), "purpose": Location.AIP_RECOVERY}
        )
        aip_recovery_location_path = Path(json.loads(resp.text)["objects"][0]["path"])

        # Clear recovery location.
        shutil.rmtree(aip_recovery_location_path)
        aip_recovery_location_path.mkdir()

        self.copy_fixture(aip_recovery_location_path)

    def request_aip_recovery(self, data: dict[str, str | int]) -> HttpResponse:
        return self.client.request_aip_recovery(self.PACKAGE_UUID, data)

    def approve_aip_recovery_request(self, event_id: int) -> HttpResponse:
        return self.client.approve_aip_recovery_request(event_id)

    def recover_aip(self) -> None:
        data: dict[str, str | int] = {
            "event_reason": "Delete please!",
            "pipeline": str(self.PIPELINE_UUID),
            "user_id": 1,
            "user_email": "user@example.com",
        }
        resp = self.request_aip_recovery(data)
        assert resp.status_code == 202

        assert Event.objects.count() == 1

        event = Event.objects.get(
            package=Package.objects.get(uuid=self.PACKAGE_UUID),
            event_type=Event.RECOVER,
            status=Event.SUBMITTED,
            event_reason=data["event_reason"],
            pipeline_id=data["pipeline"],
            user_id=data["user_id"],
            user_email=data["user_email"],
        )

        # Approve the recovery request.
        resp = self.approve_aip_recovery_request(event.id)
        assert resp.status_code == 200

        assert "Request approved: AIP restored." in resp.text

        assert Event.objects.count() == 1
        assert (
            Event.objects.filter(
                package=Package.objects.get(uuid=self.PACKAGE_UUID),
                event_type=Event.RECOVER,
                status=Event.APPROVED,
                event_reason=data["event_reason"],
                pipeline_id=data["pipeline"],
                user_id=data["user_id"],
                user_email=data["user_email"],
            ).count()
            == 1
        )

        resp = self.client.check_fixity(self.PACKAGE_UUID)
        assert resp.status_code == 200
        assert json.loads(resp.text)["success"]

    def assert_recovered(self, tmp_path: Path) -> None:
        download_path = tmp_path / "download"

        resp = self.client.download_file(self.PACKAGE_UUID)

        assert isinstance(resp, StreamingHttpResponse)
        download_path.write_bytes(b"".join(resp.streaming_content))

        # Compare the downloaded package against the original fixtures.
        if self.compressed:
            assert (
                utils.generate_checksum(download_path).hexdigest()
                == utils.generate_checksum(self.pkg).hexdigest()
            )
        else:
            assert tarfile.is_tarfile(download_path)
            extracted_path = tmp_path / "extracted"
            tarfile.TarFile(download_path).extractall(extracted_path)
            assert (
                utils.generate_checksum(extracted_path / self.pkg_name).hexdigest()
                == utils.generate_checksum(self.pkg).hexdigest()
            )


class ReingestScenario(StorageScenario):
    REINGEST_MARKER = "reingest-marker"

    def request_reingest(self, reingest_type: str) -> dict[str, Any]:
        resp = self.client.request_reingest(
            self.PACKAGE_UUID,
            {
                "pipeline": str(self.PIPELINE_UUID),
                "reingest_type": reingest_type,
            },
        )
        assert resp.status_code == 202
        return cast(dict[str, Any], json.loads(resp.text))

    def get_currently_processing_location(self) -> LocationResponseResult:
        resp = self.client.get_locations(
            {
                "pipeline_uuid": str(self.PIPELINE_UUID),
                "purpose": Location.CURRENTLY_PROCESSING,
            }
        )
        assert resp.status_code == 200
        return cast(LocationResponseResult, json.loads(resp.text)["objects"][0])

    def prepare_reingested_aip(
        self, relative_path: str, source_path: Path | None = None
    ) -> Path:
        cp_location = self.get_currently_processing_location()
        reingest_path = Path(cp_location["path"]) / "tmp" / relative_path
        if self.compressed:
            reingest_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path is None:
                source_path = FIXTURES_DIR / self.pkg
            shutil.copy2(source_path, reingest_path)
            return reingest_path
        assert reingest_path.is_dir()
        self._create_reingest_mets(reingest_path)
        return reingest_path

    def _create_reingest_mets(self, reingest_root: Path) -> Path:
        data_dir = reingest_root / "data"
        mets_files = list(data_dir.glob("METS.*.xml"))
        assert mets_files
        reingest_mets = data_dir / f"METS.{self.PACKAGE_UUID}.xml"
        shutil.copy2(mets_files[0], reingest_mets)
        content = reingest_mets.read_text()
        marker = f"<!-- {self.REINGEST_MARKER} -->"
        if marker not in content:
            if "</mets:mets>" not in content:
                raise AssertionError("METS closing tag not found")
            content = content.replace("</mets:mets>", f"{marker}\n</mets:mets>", 1)
            reingest_mets.write_text(content)
        return reingest_mets

    def finish_reingest(
        self,
        *,
        origin_location: str,
        origin_path: str,
        current_location: str,
        current_path: str,
    ) -> HttpResponse:
        data: dict[str, str | int | list[PremisEvent] | list[PremisAgent]] = {
            "uuid": str(self.PACKAGE_UUID),
            "origin_location": origin_location,
            "origin_path": origin_path,
            "current_location": current_location,
            "current_path": current_path,
            "size": Package.objects.get(uuid=self.PACKAGE_UUID).size,
            "package_type": Package.AIP,
            "aip_subtype": "Archival Information Package",
            "origin_pipeline": f"/api/v2/pipeline/{self.PIPELINE_UUID}/",
            "events": [self.get_compression_event()],
            "agents": [self.get_agent()],
            "reingest": True,
        }
        return self.client.add_file(self.PACKAGE_UUID, data)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scenario",
    [
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.NFS,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.NFS,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.NFS,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.NFS,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.NFS,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.S3,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.S3,
            replication_protocol=Space.S3,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.NFS,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.NFS,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.RCLONE,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        ReingestScenario(
            storage_protocol=Space.RCLONE,
            replication_protocol=Space.RCLONE,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
    ],
    ids=[
        "local_fs_to_nfs_compressed",
        "local_fs_to_nfs_uncompressed",
        "local_fs_to_s3_compressed",
        "local_fs_to_s3_uncompressed",
        "local_fs_to_rclone_compressed",
        "local_fs_to_rclone_uncompressed",
        "nfs_to_local_fs_compressed",
        "nfs_to_local_fs_uncompressed",
        "nfs_to_s3_compressed",
        "nfs_to_s3_uncompressed",
        "nfs_to_rclone_compressed",
        "nfs_to_rclone_uncompressed",
        "s3_to_local_fs_compressed",
        "s3_to_local_fs_uncompressed",
        "s3_to_nfs_compressed",
        "s3_to_nfs_uncompressed",
        "s3_to_s3_compressed",
        "s3_to_s3_uncompressed",
        "rclone_to_local_fs_compressed",
        "rclone_to_local_fs_uncompressed",
        "rclone_to_nfs_compressed",
        "rclone_to_nfs_uncompressed",
        "rclone_to_rclone_compressed",
        "rclone_to_rclone_uncompressed",
    ],
)
def test_reingest_with_replicas(
    startup: None,
    scenario: ReingestScenario,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
    s3_resource: ServiceResource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()

    cp_location = Location.objects.get(
        pipeline__uuid=scenario.PIPELINE_UUID,
        purpose=Location.CURRENTLY_PROCESSING,
    )
    cp_staging_path = (
        working_directory_path
        / "var"
        / "archivematica"
        / "sharedDirectory"
        / "tmp"
        / "reingest_staging"
    )
    cp_staging_path.mkdir(parents=True, exist_ok=True)
    cp_location.space.staging_path = str(cp_staging_path)
    cp_location.space.save()

    package = Package.objects.get(uuid=scenario.PACKAGE_UUID)
    current_path = package.current_path
    original_replicas = list(Package.objects.filter(replicated_package=package.uuid))
    original_replica_uuids = {replica.uuid for replica in original_replicas}
    assert len(original_replicas) == 1

    def fake_reingest(
        self: Pipeline, _name: str, _uuid: uuid.UUID, _target: str = "transfer"
    ) -> dict[str, str]:
        return {"reingest_uuid": str(uuid.uuid4())}

    monkeypatch.setattr(Pipeline, "reingest", fake_reingest)

    scenario.request_reingest(Package.FULL)

    relative_path = Path(current_path)
    relative_path_str = relative_path.as_posix()
    if not scenario.compressed:
        relative_path_str = f"{relative_path_str}/"
    source_path = Path(package.full_path)
    if scenario.compressed and not source_path.exists():
        package_any = cast(Any, package)
        source_path = Path(package_any.fetch_local_path())
    scenario.prepare_reingested_aip(relative_path_str, source_path=source_path)
    package_any = cast(Any, package)
    package_any.clear_local_tempdirs()
    origin_path = (Path("tmp") / relative_path).as_posix()
    if not scenario.compressed:
        origin_path = f"{origin_path}/"

    assert scenario.aip_storage_location_attrs is not None
    resp = scenario.finish_reingest(
        origin_location=scenario.get_currently_processing_location()["resource_uri"],
        origin_path=origin_path,
        current_location=scenario.aip_storage_location_attrs["resource_uri"],
        current_path=current_path,
    )
    assert resp.status_code in {200, 202}

    package.refresh_from_db()
    if scenario.compressed:
        assert package.full_pointer_file_path
        assert Path(package.full_pointer_file_path).is_file()
    else:
        assert package.full_pointer_file_path is None

    resp = scenario.client.check_fixity(package.uuid)
    assert resp.status_code == 200
    assert json.loads(resp.text)["success"] is True

    replicas = list(Package.objects.filter(replicated_package=package.uuid))
    deleted_replicas = [
        replica for replica in replicas if replica.status == Package.DELETED
    ]
    uploaded_replicas = [
        replica for replica in replicas if replica.status == Package.UPLOADED
    ]
    assert {replica.uuid for replica in deleted_replicas} == original_replica_uuids
    assert len(uploaded_replicas) == 1
    assert uploaded_replicas[0].uuid not in original_replica_uuids
    for replica in uploaded_replicas:
        if scenario.compressed:
            assert replica.full_pointer_file_path
            assert Path(replica.full_pointer_file_path).is_file()
        else:
            assert replica.full_pointer_file_path is None

    if scenario.replication_protocol in scenario.OBJECT_STORAGE_PROTOCOLS:
        bucket_name = scenario._object_storage_bucket_name
        assert bucket_name
        replica = uploaded_replicas[0]
        prefix = (
            Path(replica.current_location.relative_path) / replica.current_path
        ).as_posix()
        if not scenario.compressed:
            prefix = f"{prefix}/"
        matches = list(s3_resource.Bucket(bucket_name).objects.filter(Prefix=prefix))
        assert matches


@pytest.mark.parametrize(
    "scenario,corrupt_package",
    [
        (
            AIPRecoveryScenario(
                storage_protocol=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
            ),
            False,
        ),
        (
            AIPRecoveryScenario(
                storage_protocol=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
            ),
            True,
        ),
        (
            AIPRecoveryScenario(
                storage_protocol=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
            ),
            False,
        ),
        (
            AIPRecoveryScenario(
                storage_protocol=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
            ),
            True,
        ),
    ],
    ids=[
        "compressed_original",
        "compressed_corrupted",
        "uncompressed_original",
        "uncompressed_corrupted",
    ],
)
@pytest.mark.django_db
def test_aip_recovery(
    startup: None,
    scenario: AIPRecoveryScenario,
    corrupt_package: bool,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
    tmp_path: Path,
) -> None:
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()
    if corrupt_package:
        scenario.corrupt_package()
    scenario.copy_fixture_to_aip_recovery_location()
    scenario.recover_aip()
    scenario.assert_recovered(tmp_path)


@pytest.mark.django_db
def test_aip_recovery_handles_recovery_copy_setup_error(
    startup: None,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
) -> None:
    # This represents an scenario where the user does not place the recovery
    # copy in the recovery location directory, creates the recovery request
    # and approves it.
    scenario = AIPRecoveryScenario(
        storage_protocol=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
    )
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()
    scenario.corrupt_package()

    data: dict[str, str | int] = {
        "event_reason": "Delete please!",
        "pipeline": str(scenario.PIPELINE_UUID),
        "user_id": 1,
        "user_email": "user@example.com",
    }
    resp = scenario.request_aip_recovery(data)
    assert resp.status_code == 202

    assert Event.objects.count() == 1
    event = Event.objects.get(
        package=Package.objects.get(uuid=scenario.PACKAGE_UUID),
        event_type=Event.RECOVER,
        status=Event.SUBMITTED,
        event_reason=data["event_reason"],
        pipeline_id=data["pipeline"],
        user_id=data["user_id"],
        user_email=data["user_email"],
    )

    resp = scenario.approve_aip_recovery_request(event.id)
    assert resp.status_code == 200

    content = resp.text
    assert "AIP restore failed: error accessing restore files" in content
    assert "Please contact an administrator or see logs for details" in content


@pytest.fixture
def s3_resource(s3_recorded_keys: list[str]) -> ServiceResource:
    """Return a boto3 resource connected to the test MinIO instance."""
    del s3_recorded_keys  # Ensure tracking fixture executes before resource creation.
    return boto3.resource(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id="minio",
        aws_secret_access_key="minio123",
        region_name="planet-earth",
    )


def _provision_s3_bucket(
    s3_resource: ServiceResource,
    *,
    region: str,
    name_prefix: str,
    object_keys: Iterable[str] | None = None,
) -> str:
    bucket_name = f"{name_prefix}{uuid.uuid4().hex}"
    try:
        if region.lower() == "us-east-1":
            s3_resource.create_bucket(Bucket=bucket_name)
        else:
            s3_resource.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
    except ClientError as exc:
        error_code = (exc.response.get("Error") or {}).get("Code")
        if error_code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise

    if object_keys:
        for key in object_keys:
            s3_resource.Object(bucket_name, key).put(Body=b"content")

    return bucket_name


@pytest.fixture
def s3_browse_bucket(
    request: pytest.FixtureRequest, s3_resource: ServiceResource
) -> Iterator[str]:
    """Provision a bucket backed by the MinIO test service."""
    object_keys = getattr(request, "param", None)
    bucket_name = _provision_s3_bucket(
        s3_resource,
        region="planet-earth",
        name_prefix="storage-service-browse-",
        object_keys=object_keys,
    )

    yield bucket_name

    bucket = s3_resource.Bucket(bucket_name)
    bucket.objects.all().delete()
    bucket.delete()


_BROWSE_BUCKET_OBJECTS = [
    "ts/file1.txt",
    "ts/file2.txt",
    "ts/dir1/file3.txt",
    "ts/dir2/file4.txt",
    "ts/dir2/file5.txt",
    "ts/dir2/subdir1/file6.txt",
    "ts/dir2/subdir2/file7.txt",
    "ts/dir2/subdir2/subdir3/file8.txt",
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "s3_browse_bucket",
    [_BROWSE_BUCKET_OBJECTS],
    indirect=True,
)
def test_browsing_a_s3_transfer_source_location_loads_path_level_results_only(
    admin_client: DjangoTestClient,
    s3_browse_bucket: str,
    s3_recorded_keys: list[str],
    tmp_path: Path,
) -> None:
    client = Client(admin_client)
    shared_directory = tmp_path / "var" / "archivematica" / "sharedDirectory"
    shared_directory.mkdir(parents=True, exist_ok=True)

    # Create pipeline.
    resp = client.add_pipeline(
        {
            "uuid": str(uuid.uuid4()),
            "description": "My pipeline",
            "create_default_locations": False,
            "shared_path": str(shared_directory),
            "remote_name": "http://127.0.0.1:65534",
            "api_username": "test",
            "api_key": "test",
        }
    )
    assert resp.status_code == 201
    pipeline = json.loads(resp.text)

    # Create space.
    resp = client.add_space(
        {
            "access_protocol": Space.S3,
            "path": "/",
            "staging_path": "/var/archivematica/storage_service",
            "endpoint_url": "http://minio:9000",
            "access_key_id": "minio-user",
            "secret_access_key": "minio-password",
            "region": "planet-earth",
            "bucket": s3_browse_bucket,
        }
    )
    assert resp.status_code == 201
    space = json.loads(resp.text)

    # Create transfer source location.
    resp = client.add_location(
        {
            "relative_path": "ts",
            "purpose": Location.TRANSFER_SOURCE,
            "space": space["resource_uri"],
            "pipeline": [pipeline["resource_uri"]],
        }
    )
    assert resp.status_code == 201
    location = json.loads(resp.text)

    resp = client.browse_location(
        uuid.UUID(location["uuid"]), {"path": base64.b64encode(b"/ts/dir2").decode()}
    )
    assert resp.status_code == 200
    browse_result = json.loads(resp.text)

    entries = {base64.b64decode(entry).decode() for entry in browse_result["entries"]}
    directories = {
        base64.b64decode(directory).decode()
        for directory in browse_result["directories"]
    }
    assert entries == {"file4.txt", "file5.txt", "subdir1", "subdir2"}
    assert directories == {"subdir1", "subdir2"}

    # Verify the keys the browse API endpoint iterated through.
    assert set(s3_recorded_keys) == {
        "ts/dir2/file4.txt",
        "ts/dir2/file5.txt",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "s3_browse_bucket",
    [_BROWSE_BUCKET_OBJECTS],
    indirect=True,
)
def test_browsing_an_rclone_transfer_source_location_works_with_limited_permissions(
    admin_client: DjangoTestClient,
    s3_browse_bucket: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCLONE_CONFIG_MYS3_ACCESS_KEY_ID", "minio-user")
    monkeypatch.setenv("RCLONE_CONFIG_MYS3_SECRET_ACCESS_KEY", "minio-password")

    client = Client(admin_client)
    shared_directory = tmp_path / "var" / "archivematica" / "sharedDirectory"
    shared_directory.mkdir(parents=True, exist_ok=True)

    # Create pipeline.
    resp = client.add_pipeline(
        {
            "uuid": str(uuid.uuid4()),
            "description": "My pipeline",
            "create_default_locations": False,
            "shared_path": str(shared_directory),
            "remote_name": "http://127.0.0.1:65534",
            "api_username": "test",
            "api_key": "test",
        }
    )
    assert resp.status_code == 201
    pipeline = json.loads(resp.text)

    # Create space.
    resp = client.add_space(
        {
            "access_protocol": Space.RCLONE,
            "path": "/",
            "staging_path": "/var/archivematica/storage_service",
            "remote_name": "mys3",
            "container": s3_browse_bucket,
        }
    )
    assert resp.status_code == 201
    space = json.loads(resp.text)

    # Create transfer source location.
    resp = client.add_location(
        {
            "relative_path": "ts",
            "purpose": Location.TRANSFER_SOURCE,
            "space": space["resource_uri"],
            "pipeline": [pipeline["resource_uri"]],
        }
    )
    assert resp.status_code == 201
    location = json.loads(resp.text)

    resp = client.browse_location(
        uuid.UUID(location["uuid"]), {"path": base64.b64encode(b"/ts/dir2").decode()}
    )
    assert resp.status_code == 200
    browse_result = json.loads(resp.text)

    entries = {base64.b64decode(entry).decode() for entry in browse_result["entries"]}
    directories = {
        base64.b64decode(directory).decode()
        for directory in browse_result["directories"]
    }
    assert entries == {"file4.txt", "file5.txt", "subdir1", "subdir2"}
    assert directories == {"subdir1", "subdir2"}

    # The rest simulates the start of the Archivematica transfer process, where
    # the pipeline requests the Storage Service to copy files from the transfer
    # source location to the currently processing location directory.

    # Create a local file system space.
    fs_space_path = shared_directory / "tmp" / "local_fs"
    fs_space_staging_path = shared_directory / "tmp" / "local_fs_staging_path"
    fs_space_path.mkdir(parents=True)
    fs_space_staging_path.mkdir(parents=True)
    resp = client.add_space(
        {
            "access_protocol": Space.LOCAL_FILESYSTEM,
            "path": str(fs_space_path),
            "staging_path": str(fs_space_staging_path),
        }
    )
    assert resp.status_code == 201
    fs_space = json.loads(resp.text)

    # Add a currently processing location.
    resp = client.add_location(
        {
            "relative_path": "currentlyProcessing",
            "purpose": Location.CURRENTLY_PROCESSING,
            "space": fs_space["resource_uri"],
            "pipeline": [pipeline["resource_uri"]],
        }
    )
    assert resp.status_code == 201
    fs_location = json.loads(resp.text)
    fs_location_path = Path(fs_location["path"])
    fs_location_path.mkdir(parents=True)

    # Copy one file from the transfer source location to the currently
    # processing location using the API.
    source_file_name = "file1.txt"
    transfer_name = "my-transfer"
    transfer_dir = fs_location_path / transfer_name
    transfer_dir.mkdir()
    resp = client.set_location(
        uuid.UUID(fs_location["uuid"]),
        {
            "origin_location": location["resource_uri"],
            "pipeline": pipeline["resource_uri"],
            "files": [{"source": source_file_name, "destination": transfer_name}],
        },
    )
    assert resp.status_code == 200

    # Browse the processing location and ensure the file was copied.
    resp = client.browse_location(
        uuid.UUID(fs_location["uuid"]),
        {"path": base64.b64encode(transfer_name.encode()).decode()},
    )
    assert resp.status_code == 200
    fs_browse_result = json.loads(resp.text)

    entries = {
        base64.b64decode(entry).decode() for entry in fs_browse_result["entries"]
    }
    directories = {
        base64.b64decode(directory).decode()
        for directory in fs_browse_result["directories"]
    }
    assert entries == {source_file_name}
    assert directories == set()
    # File content is set in the s3_browse_bucket fixture.
    assert (transfer_dir / source_file_name).read_text() == "content"


class AIPDeletionScenario(StorageScenario):
    def request_aip_deletion(self, data: dict[str, str | int]) -> HttpResponse:
        return self.client.request_aip_deletion(self.PACKAGE_UUID, data)

    def review_aip_deletion(
        self, file_uuid: uuid.UUID, data: dict[str, str | int]
    ) -> HttpResponse:
        return self.client.review_aip_deletion(file_uuid, data)

    def delete_aip(self) -> str:
        data: dict[str, str | int] = {
            "event_reason": "Delete please!",
            "pipeline": str(self.PIPELINE_UUID),
            "user_id": 1,
            "user_email": "user@example.com",
        }
        resp = self.request_aip_deletion(data)
        assert resp.status_code == 202

        assert Event.objects.count() == 1

        event = Event.objects.get(
            package=Package.objects.get(uuid=self.PACKAGE_UUID),
            event_type=Event.DELETE,
            status=Event.SUBMITTED,
            event_reason=data["event_reason"],
            pipeline_id=data["pipeline"],
            user_id=data["user_id"],
            user_email=data["user_email"],
        )

        package = Package.objects.get(uuid=self.PACKAGE_UUID)
        assert package.current_location.space.access_protocol == self.storage_protocol
        package_full_path = str(package.full_path)

        if self.storage_protocol not in self.OBJECT_STORAGE_PROTOCOLS:
            assert Path(package_full_path).exists()

        reason = "Deleting!"
        resp = self.review_aip_deletion(
            self.PACKAGE_UUID,
            {
                "reason": reason,
                "decision": package_request.PackageRequestDecision.APPROVE,
                "event_id": event.id,
            },
        )
        assert resp.status_code == 200
        response_payload = json.loads(resp.text)
        assert response_payload == {
            "message": "Request approved: Package deleted successfully.",
        }

        assert Event.objects.count() == 1
        assert (
            Event.objects.filter(
                package=Package.objects.get(uuid=self.PACKAGE_UUID),
                event_type=Event.DELETE,
                status=Event.APPROVED,
                event_reason=data["event_reason"],
                pipeline_id=data["pipeline"],
                user_id=data["user_id"],
                user_email=data["user_email"],
            ).count()
            == 1
        )

        package.refresh_from_db()
        assert package.status == Package.DELETED

        return package_full_path

    def assert_deleted(
        self,
        package_full_path: str,
        s3_resource: ServiceResource | None,
    ) -> None:
        package = Package.objects.get(uuid=self.PACKAGE_UUID)
        assert package.status == Package.DELETED

        if self.storage_protocol in self.OBJECT_STORAGE_PROTOCOLS:
            assert s3_resource is not None
            bucket_name = self._object_storage_bucket_name
            assert bucket_name
            prefix = package_full_path.lstrip(os.sep)
            bucket = s3_resource.Bucket(bucket_name)
            remaining = list(bucket.objects.filter(Prefix=prefix))
            assert not remaining
        else:
            path = Path(package_full_path)
            assert not path.exists()


@pytest.mark.parametrize(
    "scenario",
    [
        AIPDeletionScenario(
            storage_protocol=Space.S3, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        AIPDeletionScenario(
            storage_protocol=Space.S3, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        AIPDeletionScenario(
            storage_protocol=Space.RCLONE, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        AIPDeletionScenario(
            storage_protocol=Space.RCLONE, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        AIPDeletionScenario(
            storage_protocol=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        AIPDeletionScenario(
            storage_protocol=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        AIPDeletionScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            pkg=COMPRESSED_PACKAGE,
            compressed=True,
        ),
        AIPDeletionScenario(
            storage_protocol=Space.LOCAL_FILESYSTEM,
            pkg=UNCOMPRESSED_PACKAGE,
            compressed=False,
        ),
    ],
    ids=[
        "s3_compressed",
        "s3_uncompressed",
        "rclone_compressed",
        "rclone_uncompressed",
        "nfs_compressed",
        "nfs_uncompressed",
        "local_fs_compressed",
        "local_fs_uncompressed",
    ],
)
@pytest.mark.django_db
def test_aip_deletion(
    startup: None,
    scenario: AIPDeletionScenario,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
    s3_resource: ServiceResource,
) -> None:
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()
    package_full_path = scenario.delete_aip()
    scenario.assert_deleted(
        package_full_path,
        s3_resource
        if scenario.storage_protocol in scenario.OBJECT_STORAGE_PROTOCOLS
        else None,
    )


@pytest.fixture
def gnupg_home(tmp_path: Path, settings: SettingsWrapper) -> Iterator[Path]:
    home = tmp_path / "gnupg"
    home.mkdir(parents=True, exist_ok=True)
    # GnuPG expects 0700 on the homedir.
    home.chmod(0o700)
    original_gnupg_home = settings.GNUPG_HOME_PATH
    # Reset the singleton to ensure GNUPG_HOME_PATH isolation for this test.
    original_gpg_client = gpgutils.gpg._gpg
    settings.GNUPG_HOME_PATH = str(home)
    gpgutils.gpg._gpg = None
    yield home
    settings.GNUPG_HOME_PATH = original_gnupg_home
    gpgutils.gpg._gpg = original_gpg_client


@pytest.fixture(scope="session")
def gpg_binary_path() -> str:
    try:
        return gpgutils.get_gpg_binary_path()
    except gpgutils.GPGBinaryPathError:
        pytest.skip("GnuPG not available")


class GPGStorageScenario(StorageScenario):
    SPACES = {
        **StorageScenario.SPACES,
        Space.GPG: {
            "access_protocol": Space.GPG,
            "path": "/var/archivematica/sharedDirectory/tmp/gpg_fs",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/gpg_staging_path",
        },
    }

    def __init__(
        self,
        *,
        gpg_fingerprint: str,
        pkg: Path,
        compressed: bool,
    ) -> None:
        super().__init__(
            storage_protocol=Space.GPG,
            pkg=pkg,
            compressed=compressed,
        )
        self.gpg_fingerprint = gpg_fingerprint

    def _space_definition(self, protocol: str) -> dict[str, str | bool]:
        data = super()._space_definition(protocol)
        if protocol == Space.GPG:
            data["key"] = self.gpg_fingerprint
        return data


_KEY_DETAIL_RE = re.compile(r"/keys/(?P<fingerprint>[^/]+)/detail")


def _extract_key_fingerprint(location: str) -> str:
    match = _KEY_DETAIL_RE.search(location)
    if not match:
        raise AssertionError(f"Unable to extract fingerprint from {location}")
    return match.group("fingerprint")


def _create_admin_gpg_key(
    admin_client: DjangoTestClient, *, name_real: str, name_email: str
) -> str:
    resp = admin_client.post(
        reverse("administration:key_create"),
        data={"name_real": name_real, "name_email": name_email},
    )
    assert resp.status_code == 302
    return _extract_key_fingerprint(resp.headers["Location"])


def _generate_private_key_armor(
    tmp_dir: str, *, passphrase: str | None, gpg_binary_path: str
) -> tuple[str, str]:
    source_home = Path(tmp_dir)
    source_home.chmod(0o700)
    gpg_source = gnupg.GPG(gnupghome=str(source_home), gpgbinary=gpg_binary_path)
    key_input = gpg_source.gen_key_input(
        key_type="RSA",
        key_length=2048,
        name_real="Import Test Key",
        name_email="import-test@example.com",
        passphrase=passphrase or "",
        no_protection=not passphrase,
    )
    key = gpg_source.gen_key(key_input)
    assert key
    export_kwargs: dict[str, bool | str] = {"secret": True}
    if passphrase is None:
        export_kwargs["expect_passphrase"] = False
    else:
        export_kwargs["passphrase"] = passphrase
    private_armor = gpg_source.export_keys(key.fingerprint, **export_kwargs)
    assert "BEGIN PGP PRIVATE KEY BLOCK" in private_armor
    return key.fingerprint, private_armor


@pytest.mark.django_db
def test_admin_key_lifecycle(
    admin_client: DjangoTestClient,
    gnupg_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    gpg_binary_path: str,
) -> None:
    # Reduce default key length to avoid slow key generation in low-entropy CI.
    monkeypatch.setattr(gpgutils, "DFLT_KEY_LENGTH", 2048)
    resp = admin_client.get(reverse("administration:key_list"))
    assert resp.status_code == 200

    fingerprint = _create_admin_gpg_key(
        admin_client,
        name_real="Integration Test Key",
        name_email="integration@example.com",
    )

    detail_url = reverse(
        "administration:key_detail", kwargs={"key_fingerprint": fingerprint}
    )
    resp = admin_client.get(detail_url)
    assert resp.status_code == 200
    assert fingerprint in resp.text
    assert "BEGIN PGP PUBLIC KEY BLOCK" in resp.text

    delete_url = reverse(
        "administration:key_delete", kwargs={"key_fingerprint": fingerprint}
    )
    resp = admin_client.post(delete_url, data={"__confirm__": "1"}, follow=True)
    assert resp.status_code == 200

    resp = admin_client.get(detail_url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_admin_key_imports_unpassphrased_key(
    admin_client: DjangoTestClient,
    gnupg_home: Path,
    gpg_binary_path: str,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="gnupg-fixture-") as tmp_dir:
        fingerprint, private_armor = _generate_private_key_armor(
            tmp_dir, passphrase=None, gpg_binary_path=gpg_binary_path
        )
    resp = admin_client.post(
        reverse("administration:key_import"),
        data={"ascii_armor": private_armor},
    )
    assert resp.status_code == 302

    list_resp = admin_client.get(reverse("administration:key_list"))
    assert fingerprint in list_resp.text

    delete_url = reverse(
        "administration:key_delete", kwargs={"key_fingerprint": fingerprint}
    )
    resp = admin_client.post(delete_url, data={"__confirm__": "1"}, follow=True)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_key_import_rejects_passphrased_key(
    admin_client: DjangoTestClient,
    gnupg_home: Path,
    gpg_binary_path: str,
) -> None:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="gnupg-fixture-") as tmp_dir:
        fingerprint, private_armor = _generate_private_key_armor(
            tmp_dir, passphrase="secret", gpg_binary_path=gpg_binary_path
        )
    resp = admin_client.post(
        reverse("administration:key_import"),
        data={"ascii_armor": private_armor},
    )
    assert resp.status_code == 200
    message_list = list(resp.context["messages"])
    assert any(message.level == messages.ERROR for message in message_list)
    assert (
        "Import failed. The GPG key provided requires a passphrase. "
        "GPG keys with passphrases cannot be imported" in resp.text
    )

    list_resp = admin_client.get(reverse("administration:key_list"))
    assert fingerprint not in list_resp.text


@pytest.mark.django_db
def test_gpg_space_encrypts_and_decrypts_aip(
    startup: None,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    tmp_path: Path,
    gnupg_home: Path,
    gpg_binary_path: str,
) -> None:
    fingerprint = _create_admin_gpg_key(
        admin_client,
        name_real="GPG Space Test",
        name_email="gpg-space@example.com",
    )

    scenario = GPGStorageScenario(
        gpg_fingerprint=fingerprint,
        pkg=COMPRESSED_PACKAGE,
        compressed=True,
    )
    scenario.init(
        admin_client,
        working_directory_path,
    )
    scenario.store_aip()
    scenario.assert_stored()

    package = Package.objects.get(uuid=scenario.PACKAGE_UUID)
    assert package.encryption_key_fingerprint == fingerprint
    encrypted_path = Path(package.full_path)
    assert encrypted_path.is_file()
    assert (
        utils.generate_checksum(encrypted_path).hexdigest()
        != utils.generate_checksum(scenario.pkg).hexdigest()
    )

    download_path = tmp_path / "downloaded.7z"
    resp = scenario.client.download_file(scenario.PACKAGE_UUID)
    assert isinstance(resp, StreamingHttpResponse)
    download_path.write_bytes(b"".join(resp.streaming_content))
    assert (
        utils.generate_checksum(download_path).hexdigest()
        == utils.generate_checksum(scenario.pkg).hexdigest()
    )
