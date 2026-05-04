"""Integration testing.

This module tests Archivematica Storage Service in isolation. It does not
require Archivematica pipelines deployed.

Currently, the tests in this module are executed via Docker Compose. It may be
worth investigating a setup where pytest orchestrates Compose services instead.

Missing: encryption, multiple replicators, packages generated with older versions
of Archivematica, etc...
"""

from __future__ import annotations

import base64
import datetime
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
from typing import TYPE_CHECKING
from typing import Protocol
from typing import TypedDict
from typing import cast

import boto3
import gnupg
import pytest
from botocore.exceptions import ClientError
from django.contrib import messages
from django.core.management import call_command
from django.http import StreamingHttpResponse
from django.test import Client as DjangoTestClient
from django.urls import reverse
from django.utils import timezone
from lxml import etree
from metsrw.plugins import premisrw
from pytest_django.fixtures import SettingsWrapper

from archivematica.storage_service.common import gpgutils
from archivematica.storage_service.common import utils
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations.models import Event
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models import Space
from archivematica.storage_service.storage_service import __version__ as ss_version

if TYPE_CHECKING:
    from mypy_boto3_s3.service_resource import S3ServiceResource
    from mypy_boto3_s3.type_defs import CreateBucketConfigurationTypeDef

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

    def __getitem__(self, header: str) -> str: ...

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

    def extract_file(self, file_id: uuid.UUID, data: dict[str, str]) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/extract_file/", data)


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

    def aip_mets_relative_path(self) -> str:
        if self.compressed:
            package_root = self.pkg.name.removesuffix("".join(self.pkg.suffixes))
            mets_filename = f"METS.{self.PACKAGE_UUID}.xml"
        else:
            mets_files = list(self.pkg.glob("data/METS.*.xml"))
            assert len(mets_files) == 1
            package_root = self.pkg_name
            mets_filename = mets_files[0].name

        return f"{package_root}/data/{mets_filename}"

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
def s3_resource(s3_recorded_keys: list[str]) -> S3ServiceResource:
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
    s3_resource: S3ServiceResource,
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
                # MinIO accepts non-AWS region names; boto3 stubs restrict this to AWS literals.
                CreateBucketConfiguration=cast(
                    "CreateBucketConfigurationTypeDef",
                    {"LocationConstraint": region},
                ),
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
    request: pytest.FixtureRequest, s3_resource: S3ServiceResource
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
        return self.delete_package(self.PACKAGE_UUID, self.storage_protocol)

    def delete_package(self, file_uuid: uuid.UUID, expected_protocol: str) -> str:
        data: dict[str, str | int] = {
            "event_reason": "Delete please!",
            "pipeline": str(self.PIPELINE_UUID),
            "user_id": 1,
            "user_email": "user@example.com",
        }
        resp = self.client.request_aip_deletion(file_uuid, data)
        assert resp.status_code == 202

        assert Event.objects.count() == 1

        event = Event.objects.get(
            package=Package.objects.get(uuid=file_uuid),
            event_type=Event.DELETE,
            status=Event.SUBMITTED,
            event_reason=data["event_reason"],
            pipeline_id=data["pipeline"],
            user_id=data["user_id"],
            user_email=data["user_email"],
        )

        package = Package.objects.get(uuid=file_uuid)
        assert package.current_location.space.access_protocol == expected_protocol
        package_full_path = str(package.full_path)

        if expected_protocol not in self.OBJECT_STORAGE_PROTOCOLS:
            assert Path(package_full_path).exists()

        reason = "Deleting!"
        resp = self.review_aip_deletion(
            file_uuid,
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
                package=Package.objects.get(uuid=file_uuid),
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
        s3_resource: S3ServiceResource | None,
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
    s3_resource: S3ServiceResource,
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


def assert_mets_response(resp: HttpResponse) -> bytes:
    assert resp.status_code == 200
    assert isinstance(resp, StreamingHttpResponse)
    content = b"".join(resp.streaming_content)

    assert b"<mets:mets" in content

    return content


def assert_download_filename(resp: HttpResponse, filename: str) -> None:
    assert resp["Content-Disposition"] == f'attachment; filename="{filename}"'


def get_xml_element(root: etree._Element, path: str) -> etree._Element:
    elements = root.findall(path, namespaces=utils.NSMAP)

    assert len(elements) == 1

    return elements[0]


def get_mets_createdate(mets_content: bytes) -> str:
    mets_root = etree.fromstring(mets_content)
    mets_header = get_xml_element(mets_root, "mets:metsHdr")
    createdate = mets_header.get("CREATEDATE")

    assert createdate

    return createdate


def current_storage_timestamp() -> datetime.datetime:
    return timezone.now().replace(microsecond=0, tzinfo=None)


def parse_storage_timestamp(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")


def get_xml_elements_by_local_name(
    root: etree._Element, local_name: str
) -> list[etree._Element]:
    return [
        element
        for element in root.iter()
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == local_name
    ]


def get_child_text(element: etree._Element, child_name: str) -> str:
    children = get_xml_elements_by_local_name(element, child_name)

    assert len(children) == 1
    assert children[0].text

    return children[0].text


def get_premis_event(root: etree._Element, event_type: str) -> etree._Element:
    events = [
        event
        for event in get_xml_elements_by_local_name(root, "event")
        if get_child_text(event, "eventType") == event_type
    ]

    assert len(events) == 1

    return events[0]


@pytest.mark.parametrize(
    ("storage_protocol", "replication_protocol"),
    [
        (Space.S3, Space.S3),
        (Space.S3, Space.RCLONE),
        (Space.S3, Space.NFS),
        (Space.S3, Space.LOCAL_FILESYSTEM),
        (Space.RCLONE, Space.S3),
        (Space.RCLONE, Space.RCLONE),
        (Space.RCLONE, Space.NFS),
        (Space.RCLONE, Space.LOCAL_FILESYSTEM),
    ],
    ids=[
        "s3_to_s3",
        "s3_to_rclone",
        "s3_to_nfs",
        "s3_to_local_fs",
        "rclone_to_s3",
        "rclone_to_rclone",
        "rclone_to_nfs",
        "rclone_to_local_fs",
    ],
)
@pytest.mark.django_db
def test_repair_aip_pointer_file_after_remote_replica_deletion(
    startup: None,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
    storage_protocol: str,
    replication_protocol: str,
) -> None:
    # Store a compressed AIP in remote storage and create its replica.
    scenario = AIPDeletionScenario(
        storage_protocol=storage_protocol,
        replication_protocol=replication_protocol,
        pkg=COMPRESSED_PACKAGE,
        compressed=True,
    )
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()

    # In the current code, these remote-source replicas share the original AIP
    # pointer.
    aip = Package.objects.get(uuid=scenario.PACKAGE_UUID)
    replica = Package.objects.get(replicated_package=aip.uuid)
    aip_pointer_path = Path(str(aip.full_pointer_file_path))
    mets_relative_path = scenario.aip_mets_relative_path()

    assert replica.pointer_file_location == aip.pointer_file_location
    assert replica.pointer_file_path == aip.pointer_file_path
    assert aip.full_pointer_file_path is not None
    assert aip_pointer_path.exists()

    # The original AIP METS is extractable before the shared pointer is deleted.
    resp = scenario.client.extract_file(
        aip.uuid, {"relative_path_to_file": mets_relative_path}
    )
    aip_mets_createdate = get_mets_createdate(assert_mets_response(resp))

    # Deleting the replica deletes the shared pointer file but keeps the AIP row.
    scenario.delete_package(replica.uuid, replication_protocol)
    aip.refresh_from_db()
    replica.refresh_from_db()

    assert aip.status == Package.UPLOADED
    assert replica.status == Package.DELETED
    assert not aip_pointer_path.exists()

    # Without its pointer file, the original compressed AIP cannot be extracted.
    missing_pointer_error = rf"Error reading file.*{re.escape(str(aip_pointer_path))}.*No such file or directory"
    with pytest.raises(OSError, match=missing_pointer_error):
        scenario.client.extract_file(
            aip.uuid, {"relative_path_to_file": mets_relative_path}
        )

    # Recreate the missing original AIP pointer from the stored package content.
    repair_started_at = current_storage_timestamp()
    call_command("repair_aip_pointer_files", str(aip.uuid))
    repair_finished_at = current_storage_timestamp()
    aip.refresh_from_db()

    assert aip.full_pointer_file_path == str(aip_pointer_path)
    assert aip_pointer_path.exists()

    # The command recalculates the stored AIP file size and checksum.
    expected_checksum_algorithm = Package.DEFAULT_CHECKSUM_ALGORITHM
    expected_checksum = utils.generate_checksum(
        scenario.pkg, expected_checksum_algorithm
    ).hexdigest()
    expected_size = get_size(scenario.pkg)

    assert aip.checksum == expected_checksum
    assert aip.checksum_algorithm == expected_checksum_algorithm
    assert aip.size == expected_size

    # Download the repaired pointer through the API.
    pointer_resp = scenario.client.get_pointer_file(aip.uuid)

    assert pointer_resp.status_code == 200
    assert isinstance(pointer_resp, StreamingHttpResponse)

    # The command records the recalculated size and checksum in the pointer
    # PREMIS object.
    expected_7z_version = utils.get_7z_version()
    expected_agent_identifier = f"Archivematica-Storage-Service-{ss_version}"
    expected_file_id = aip.construct_file_id_for_pointer(aip.full_path)
    pointer_root = etree.fromstring(b"".join(pointer_resp.streaming_content))
    mets_header = get_xml_element(pointer_root, "mets:metsHdr")
    amd_sec = get_xml_element(pointer_root, "mets:amdSec")
    tech_md = get_xml_element(amd_sec, "mets:techMD")
    digiprov_mds = amd_sec.findall("mets:digiprovMD", namespaces=utils.NSMAP)
    premis_object = get_xml_element(pointer_root, ".//premis3:object")
    pointer_createdate = mets_header.get("CREATEDATE")
    amd_sec_id = amd_sec.get("ID")
    digiprov_md_ids = [digiprov_md.get("ID") for digiprov_md in digiprov_mds]

    assert pointer_root.tag == f"{{{utils.NSMAP['mets']}}}mets"
    assert (
        pointer_root.get(f"{{{utils.NSMAP['xsi']}}}schemaLocation")
        == "http://www.loc.gov/METS/ "
        "http://www.loc.gov/standards/mets/version1121/mets.xsd"
    )
    assert pointer_createdate
    assert repair_started_at <= parse_storage_timestamp(pointer_createdate)
    assert parse_storage_timestamp(pointer_createdate) <= repair_finished_at
    assert amd_sec_id
    assert tech_md.get("ID")
    assert tech_md.get("CREATED") == pointer_createdate
    assert tech_md.get("STATUS") == "current"
    assert get_xml_element(tech_md, "mets:mdWrap").get("MDTYPE") == "PREMIS:OBJECT"
    assert len(digiprov_md_ids) == 2
    assert len(set(digiprov_md_ids)) == 2
    assert all(digiprov_md_ids)
    assert [digiprov_md.get("CREATED") for digiprov_md in digiprov_mds] == [
        pointer_createdate,
        pointer_createdate,
    ]
    assert [
        get_xml_element(digiprov_md, "mets:mdWrap").get("MDTYPE")
        for digiprov_md in digiprov_mds
    ] == ["PREMIS:EVENT", "PREMIS:AGENT"]
    assert len(pointer_root.findall(".//premis3:object", namespaces=utils.NSMAP)) == 1
    assert premis_object.get(f"{{{utils.NSMAP['xsi']}}}type") == "premis:file"
    assert (
        premis_object.findtext(
            "premis3:objectIdentifier/premis3:objectIdentifierType",
            namespaces=utils.NSMAP,
        )
        == "UUID"
    )
    assert premis_object.findtext(
        "premis3:objectIdentifier/premis3:objectIdentifierValue",
        namespaces=utils.NSMAP,
    ) == str(aip.uuid)
    assert (
        premis_object.findtext(
            "premis3:objectCharacteristics/premis3:compositionLevel",
            namespaces=utils.NSMAP,
        )
        == "1"
    )
    assert (
        premis_object.findtext(
            ".//premis3:messageDigestAlgorithm",
            namespaces=utils.NSMAP,
        )
        == expected_checksum_algorithm
    )
    assert (
        premis_object.findtext(".//premis3:messageDigest", namespaces=utils.NSMAP)
        == expected_checksum
    )
    assert premis_object.findtext(
        "premis3:objectCharacteristics/premis3:size",
        namespaces=utils.NSMAP,
    ) == str(expected_size)
    assert (
        premis_object.findtext(".//premis3:formatName", namespaces=utils.NSMAP)
        == "7Zip format"
    )
    assert (
        premis_object.findtext(".//premis3:formatRegistryName", namespaces=utils.NSMAP)
        == "PRONOM"
    )
    assert (
        premis_object.findtext(".//premis3:formatRegistryKey", namespaces=utils.NSMAP)
        == utils.PRONOM_7Z
    )
    assert (
        premis_object.findtext(
            ".//premis3:creatingApplicationName",
            namespaces=utils.NSMAP,
        )
        == "7z"
    )
    assert (
        premis_object.findtext(
            ".//premis3:creatingApplicationVersion",
            namespaces=utils.NSMAP,
        )
        == expected_7z_version
    )
    assert (
        premis_object.findtext(
            ".//premis3:dateCreatedByApplication",
            namespaces=utils.NSMAP,
        )
        == aip_mets_createdate
    )

    # The repaired pointer should preserve the embedded AIP METS creation time
    # in the synthetic compression event.
    compression_event = get_xml_element(pointer_root, ".//premis3:event")

    assert (
        compression_event.findtext(
            "premis3:eventIdentifier/premis3:eventIdentifierType",
            namespaces=utils.NSMAP,
        )
        == "UUID"
    )
    assert uuid.UUID(
        compression_event.findtext(
            "premis3:eventIdentifier/premis3:eventIdentifierValue",
            namespaces=utils.NSMAP,
        )
    )
    assert (
        compression_event.findtext("premis3:eventType", namespaces=utils.NSMAP)
        == "compression"
    )
    assert (
        compression_event.findtext("premis3:eventDateTime", namespaces=utils.NSMAP)
        == aip_mets_createdate
    )
    assert (
        compression_event.findtext(
            "premis3:eventDetailInformation/premis3:eventDetail",
            namespaces=utils.NSMAP,
        )
        == f"program=7z; version={expected_7z_version}; algorithm=bzip2"
    )
    assert (
        compression_event.findtext(
            "premis3:eventOutcomeInformation/premis3:eventOutcome",
            namespaces=utils.NSMAP,
        )
        == "success"
    )
    assert (
        compression_event.findtext(
            "premis3:eventOutcomeInformation/premis3:eventOutcomeDetail/"
            "premis3:eventOutcomeDetailNote",
            namespaces=utils.NSMAP,
        )
        == "Pointer file recreated from stored AIP package content."
    )
    assert (
        compression_event.findtext(
            "premis3:linkingAgentIdentifier/premis3:linkingAgentIdentifierType",
            namespaces=utils.NSMAP,
        )
        == "preservation system"
    )
    assert (
        compression_event.findtext(
            "premis3:linkingAgentIdentifier/premis3:linkingAgentIdentifierValue",
            namespaces=utils.NSMAP,
        )
        == expected_agent_identifier
    )

    # The command records the Storage Service as the only PREMIS agent.
    premis_agent = get_xml_element(pointer_root, ".//premis3:agent")

    assert (
        premis_agent.findtext(
            "premis3:agentIdentifier/premis3:agentIdentifierType",
            namespaces=utils.NSMAP,
        )
        == "preservation system"
    )
    assert (
        premis_agent.findtext(
            "premis3:agentIdentifier/premis3:agentIdentifierValue",
            namespaces=utils.NSMAP,
        )
        == expected_agent_identifier
    )
    assert (
        premis_agent.findtext("premis3:agentName", namespaces=utils.NSMAP)
        == "Archivematica Storage Service"
    )
    assert (
        premis_agent.findtext("premis3:agentType", namespaces=utils.NSMAP) == "software"
    )

    # The METS file section points at the stored AIP and records how to
    # decompress it.
    file_group = get_xml_element(pointer_root, ".//mets:fileGrp")
    aip_file = get_xml_element(file_group, "mets:file")
    file_location = get_xml_element(aip_file, "mets:FLocat")
    transform_file = get_xml_element(aip_file, "mets:transformFile")
    physical_div = get_xml_element(
        pointer_root,
        ".//mets:structMap[@TYPE='physical']/mets:div",
    )
    physical_struct_map = get_xml_element(
        pointer_root, ".//mets:structMap[@TYPE='physical']"
    )
    physical_file_pointer = get_xml_element(physical_div, "mets:fptr")
    logical_div = get_xml_element(
        pointer_root,
        ".//mets:structMap[@TYPE='logical']/mets:div",
    )
    logical_struct_map = get_xml_element(
        pointer_root, ".//mets:structMap[@TYPE='logical']"
    )

    assert file_group.get("USE") == "Archival Information Package"
    assert aip_file.get("ID") == expected_file_id
    assert aip_file.get("GROUPID") == f"Group-{aip.uuid}"
    assert aip_file.get("ADMID") == amd_sec_id
    assert file_location.get(f"{{{utils.NSMAP['xlink']}}}href") == aip.full_path
    assert file_location.get("LOCTYPE") == "OTHER"
    assert file_location.get("OTHERLOCTYPE") == "SYSTEM"
    assert transform_file.get("TRANSFORMALGORITHM") == utils.COMPRESS_ALGO_BZIP2
    assert transform_file.get("TRANSFORMORDER") == "1"
    assert transform_file.get("TRANSFORMTYPE") == utils.DECOMPRESS_TRANSFORM_TYPE
    assert physical_struct_map.get("ID") == "structMap_1"
    assert physical_div.get("TYPE") == "Archival Information Package"
    assert physical_div.get("LABEL") == Path(aip.full_path).name
    assert physical_file_pointer.get("FILEID") == expected_file_id
    assert logical_struct_map.get("ID") == "structMap_2"
    assert logical_div.get("TYPE") == "Archival Information Package"
    assert logical_div.get("LABEL") == Path(aip.full_path).name

    # The repaired pointer restores METS extraction for the original AIP.
    resp = scenario.client.extract_file(
        aip.uuid, {"relative_path_to_file": mets_relative_path}
    )
    assert_mets_response(resp)


@pytest.mark.parametrize(
    ("storage_protocol", "replication_protocol"),
    [
        (Space.S3, Space.S3),
        (Space.S3, Space.RCLONE),
        (Space.S3, Space.NFS),
        (Space.S3, Space.LOCAL_FILESYSTEM),
        (Space.RCLONE, Space.S3),
        (Space.RCLONE, Space.RCLONE),
        (Space.RCLONE, Space.NFS),
        (Space.RCLONE, Space.LOCAL_FILESYSTEM),
    ],
    ids=[
        "s3_to_s3",
        "s3_to_rclone",
        "s3_to_nfs",
        "s3_to_local_fs",
        "rclone_to_s3",
        "rclone_to_rclone",
        "rclone_to_nfs",
        "rclone_to_local_fs",
    ],
)
@pytest.mark.django_db
def test_repair_replica_pointer_file_before_replica_deletion(
    startup: None,
    admin_client: DjangoTestClient,
    working_directory_path: Path,
    s3_browse_bucket: str,
    storage_protocol: str,
    replication_protocol: str,
) -> None:
    # Store a compressed AIP in remote storage and create its replica.
    scenario = AIPDeletionScenario(
        storage_protocol=storage_protocol,
        replication_protocol=replication_protocol,
        pkg=COMPRESSED_PACKAGE,
        compressed=True,
    )
    scenario.init(
        admin_client,
        working_directory_path,
        s3_bucket=s3_browse_bucket,
    )
    scenario.store_aip()
    scenario.assert_stored()

    # In the current code, these remote-source replicas share the original AIP
    # pointer.
    aip = Package.objects.get(uuid=scenario.PACKAGE_UUID)
    replica = Package.objects.get(replicated_package=aip.uuid)
    aip_pointer_path = Path(str(aip.full_pointer_file_path))
    mets_relative_path = scenario.aip_mets_relative_path()

    assert replica.pointer_file_location == aip.pointer_file_location
    assert replica.pointer_file_path == aip.pointer_file_path
    assert aip_pointer_path.exists()

    # Before repair, the replica endpoint still downloads the original AIP
    # pointer file.
    pointer_resp = scenario.client.get_pointer_file(replica.uuid)

    assert pointer_resp.status_code == 200
    assert_download_filename(pointer_resp, aip_pointer_path.name)

    # Repair the uploaded replica so it has its own pointer file before deletion.
    call_command("repair_replica_pointer_files", str(replica.uuid))
    aip.refresh_from_db()
    replica.refresh_from_db()
    refreshed_aip_pointer_path = Path(str(aip.full_pointer_file_path))
    replica_pointer_path = Path(str(replica.full_pointer_file_path))

    assert aip.status == Package.UPLOADED
    assert replica.status == Package.UPLOADED
    assert refreshed_aip_pointer_path == aip_pointer_path
    assert refreshed_aip_pointer_path.exists()
    assert replica.pointer_file_path != aip.pointer_file_path
    assert replica_pointer_path != refreshed_aip_pointer_path
    assert replica_pointer_path.exists()

    # Download the repaired replica pointer through the API.
    pointer_resp = scenario.client.get_pointer_file(replica.uuid)

    assert pointer_resp.status_code == 200
    assert isinstance(pointer_resp, StreamingHttpResponse)
    assert_download_filename(pointer_resp, replica_pointer_path.name)

    # The command recalculates the uploaded replica size and checksum, and the
    # replica pointer records the replica UUID with a relationship back to the
    # original AIP.
    expected_checksum_algorithm = Package.DEFAULT_CHECKSUM_ALGORITHM
    expected_checksum = utils.generate_checksum(
        scenario.pkg, expected_checksum_algorithm
    ).hexdigest()
    expected_size = get_size(scenario.pkg)
    expected_file_id = replica.construct_file_id_for_pointer(replica.full_path)
    pointer_root = etree.fromstring(b"".join(pointer_resp.streaming_content))
    premis_object = get_xml_element(pointer_root, ".//premis3:object")
    relationship = get_xml_element(premis_object, ".//premis3:relationship")

    assert replica.checksum == expected_checksum
    assert replica.checksum_algorithm == expected_checksum_algorithm
    assert replica.size == expected_size
    assert pointer_root.tag == f"{{{utils.NSMAP['mets']}}}mets"
    assert len(pointer_root.findall(".//premis3:object", namespaces=utils.NSMAP)) == 1
    assert premis_object.findtext(
        "premis3:objectIdentifier/premis3:objectIdentifierValue",
        namespaces=utils.NSMAP,
    ) == str(replica.uuid)
    assert (
        premis_object.findtext(
            ".//premis3:messageDigestAlgorithm",
            namespaces=utils.NSMAP,
        )
        == expected_checksum_algorithm
    )
    assert (
        premis_object.findtext(".//premis3:messageDigest", namespaces=utils.NSMAP)
        == expected_checksum
    )
    assert premis_object.findtext(
        "premis3:objectCharacteristics/premis3:size",
        namespaces=utils.NSMAP,
    ) == str(expected_size)
    assert (
        relationship.findtext("premis3:relationshipType", namespaces=utils.NSMAP)
        == "derivation"
    )
    assert relationship.findtext(
        "premis3:relatedObjectIdentifier/premis3:relatedObjectIdentifierValue",
        namespaces=utils.NSMAP,
    ) == str(aip.uuid)
    assert uuid.UUID(
        relationship.findtext(
            "premis3:relatedEventIdentifier/premis3:relatedEventIdentifierValue",
            namespaces=utils.NSMAP,
        )
    )

    # The replica pointer keeps the original compression event and adds replica
    # creation and validation events.
    event_types = sorted(
        get_child_text(event, "eventType")
        for event in get_xml_elements_by_local_name(pointer_root, "event")
    )
    creation_event = get_premis_event(pointer_root, "creation")
    validation_event = get_premis_event(pointer_root, "validation")

    assert event_types == ["compression", "creation", "validation"]
    assert (
        creation_event.findtext(
            "premis3:eventOutcomeInformation/premis3:eventOutcomeDetail/"
            "premis3:eventOutcomeDetailNote",
            namespaces=utils.NSMAP,
        )
        == f"Created Archival Information Package (AIP) {replica.uuid} by "
        f"replicating previously created AIP {aip.uuid}"
    )
    assert (
        validation_event.findtext(
            "premis3:eventOutcomeInformation/premis3:eventOutcome",
            namespaces=utils.NSMAP,
        )
        == "success"
    )
    assert (
        validation_event.findtext(
            "premis3:eventOutcomeInformation/premis3:eventOutcomeDetail/"
            "premis3:eventOutcomeDetailNote",
            namespaces=utils.NSMAP,
        )
        == f"Original AIP {aip.uuid} and replica AIP {replica.uuid} both have "
        f"checksum {expected_checksum} when using algorithm "
        f"{expected_checksum_algorithm}."
    )

    # The METS file section points at the stored replica and records how to
    # decompress it.
    file_group = get_xml_element(pointer_root, ".//mets:fileGrp")
    replica_file = get_xml_element(file_group, "mets:file")
    file_location = get_xml_element(replica_file, "mets:FLocat")
    transform_file = get_xml_element(replica_file, "mets:transformFile")

    assert file_group.get("USE") == "Archival Information Package"
    assert replica_file.get("ID") == expected_file_id
    assert replica_file.get("GROUPID") == f"Group-{replica.uuid}"
    assert file_location.get(f"{{{utils.NSMAP['xlink']}}}href") == replica.full_path
    assert file_location.get("LOCTYPE") == "OTHER"
    assert file_location.get("OTHERLOCTYPE") == "SYSTEM"
    assert transform_file.get("TRANSFORMALGORITHM") == utils.COMPRESS_ALGO_BZIP2
    assert transform_file.get("TRANSFORMORDER") == "1"
    assert transform_file.get("TRANSFORMTYPE") == utils.DECOMPRESS_TRANSFORM_TYPE

    # The repaired pointer supports extraction from the replica.
    resp = scenario.client.extract_file(
        replica.uuid, {"relative_path_to_file": mets_relative_path}
    )
    assert_mets_response(resp)

    # Deleting the replica deletes only the replica pointer and keeps the
    # original AIP pointer usable.
    scenario.delete_package(replica.uuid, replication_protocol)
    aip.refresh_from_db()
    replica.refresh_from_db()

    assert aip.status == Package.UPLOADED
    assert replica.status == Package.DELETED
    assert aip_pointer_path.exists()
    assert not replica_pointer_path.exists()

    resp = scenario.client.extract_file(
        aip.uuid, {"relative_path_to_file": mets_relative_path}
    )
    assert_mets_response(resp)


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
    gpg_source: gnupg.GPG = gnupg.GPG(
        gnupghome=str(source_home), gpgbinary=gpg_binary_path
    )
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
    if passphrase is None:
        private_armor = gpg_source.export_keys(
            key.fingerprint,
            secret=True,
            expect_passphrase=False,
        )
    else:
        private_armor = gpg_source.export_keys(
            key.fingerprint,
            secret=True,
            passphrase=passphrase,
        )
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
