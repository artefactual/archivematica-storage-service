"""Integration testing.

This module tests Archivematica Storage Service in isolation. It does not
require Archivematica pipelines deployed.

Currently, the tests in this module are executed via Docker Compose. It may be
worth investigating a setup where pytest orchestrates Compose services instead.

Missing: encryption, multiple replicators, packages generated with older versions
of Archivematica, etc...
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

import pytest
from common import utils
from django.core.management import call_command
from django.http import HttpResponse
from django.http import StreamingHttpResponse
from django.test import Client as TestClient
from django.urls import reverse
from locations.models import Event
from locations.models import Location
from locations.models import Package
from locations.models import Space
from lxml import etree
from metsrw.plugins import premisrw

from storage_service import __version__ as ss_version

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)

TagName = str
Attribute = str
Value = str
Element = Tuple[Attribute, Value]

PremisAgent = Tuple[
    TagName,
    Dict[str, str],
    Tuple[TagName, Element, Element],
    Element,
    Element,
]

PremisEvent = Tuple[
    TagName,
    Dict[str, str],
    Tuple[TagName, Element, Element],
    Element,
    Element,
    Element,
    Tuple[TagName, Tuple[TagName, Element]],
    Tuple[TagName, Element, Element],
]

FIXTURES_DIR = Path(__file__).parent / "fixtures"

COMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513054116-5658e603-277b-4292-9b58-20bf261c8f88.7z"
)
UNCOMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513060703-828c44bb-e631-4137-8638-bda4434218dc"
)


class Client:
    """Slim API client."""

    def __init__(self, admin_client: TestClient) -> None:
        self.admin_client = admin_client

    def add_space(self, data: Dict[str, Union[str, bool]]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/space/", json.dumps(data), content_type="application/json"
        )

    def add_pipeline(self, data: Dict[str, Union[str, bool]]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/pipeline/", json.dumps(data), content_type="application/json"
        )

    def get_pipelines(self, data: Dict[str, str]) -> HttpResponse:
        return self.admin_client.get("/api/v2/pipeline/", data)

    def add_location(self, data: Dict[str, Union[str, List[str]]]) -> HttpResponse:
        return self.admin_client.post(
            "/api/v2/location/", json.dumps(data), content_type="application/json"
        )

    def set_location(
        self, location_id: uuid.UUID, data: Dict[str, str]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/location/{location_id}/",
            json.dumps(data),
            content_type="application/json",
        )

    def get_locations(self, data: Dict[str, str]) -> HttpResponse:
        return self.admin_client.get("/api/v2/location/", data)

    def add_file(
        self,
        file_id: uuid.UUID,
        data: Dict[str, Union[str, int, List[PremisEvent], List[PremisAgent]]],
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
        self, file_id: uuid.UUID, data: Dict[str, Union[str, int]]
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
            {"approve": "Approve", f"{event_id}-status_reason": "Approved!"},
            follow=True,
        )

    def request_aip_deletion(
        self, file_id: uuid.UUID, data: Dict[str, Union[str, int]]
    ) -> HttpResponse:
        return self.admin_client.post(
            f"/api/v2/file/{file_id}/delete_aip/",
            json.dumps(data),
            content_type="application/json",
        )

    def approve_aip_deletion_request(self, event_id: int) -> HttpResponse:
        # Not possible via API.
        return self.admin_client.post(
            reverse("locations:package_delete_request"),
            {"approve": "Approve", f"{event_id}-status_reason": "Deleting!"},
            follow=True,
        )

    def download_file(self, file_id: uuid.UUID) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/download/")

    def extract_file(self, file_id: uuid.UUID, data: Dict[str, str]) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/extract_file/", data)


@pytest.fixture(scope="session")
def client(admin_client: TestClient) -> Client:
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
    from common.startup import startup

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

    SPACES: Dict[str, Dict[str, Union[str, bool]]] = {
        Space.S3: {
            "access_protocol": Space.S3,
            "path": "",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/rp_staging_path",
            "endpoint_url": "http://minio:9000",
            "access_key_id": "minio",
            "secret_access_key": "minio123",
            "region": "planet-earth",
            "bucket": "aip-storage",
        },
        Space.RCLONE: {
            "access_protocol": Space.RCLONE,
            "path": "",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/rp_staging_path",
            "remote_name": "mys3",
            "container": "mybucket",
        },
        Space.NFS: {
            "access_protocol": Space.NFS,
            "path": "/var/archivematica/sharedDirectory/tmp/nfs_mount",
            "staging_path": "/var/archivematica/sharedDirectory/tmp/rp_staging_path",
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
        src: str,
        dst: str,
        pkg: Path,
        compressed: bool,
        use_registered_aip_storage_location: bool = False,
    ) -> None:
        self.src = src
        self.dst = dst
        self.aip_storage_location_path = ""
        self.aip_storage_location_resource_uri = ""
        self.aip_storage_location_uuid = ""
        self.use_registered_aip_storage_location = use_registered_aip_storage_location
        self.pkg = pkg
        self.pkg_name = (
            f"foobar-{self.PACKAGE_UUID}{''.join(pkg.suffixes) if compressed else ''}"
        )
        self.compressed = compressed

    def init(self, admin_client: TestClient, working_directory_path: Path) -> None:
        self.client = Client(admin_client)
        self.shared_directory_path = (
            working_directory_path / "var" / "archivematica" / "sharedDirectory"
        )
        self.register_pipeline()
        self.register_aip_storage_location()
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

    def _adjust_space_data(
        self, data: Dict[str, Union[str, bool]]
    ) -> Dict[str, Union[str, bool]]:
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
        resp = self.client.add_space(self._adjust_space_data(self.SPACES[self.src]))
        assert resp.status_code == 201
        space = json.loads(resp.content)

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
        location = json.loads(resp.content)
        self.aip_storage_location_path = location["path"]
        self.aip_storage_location_resource_uri = location["resource_uri"]
        self.aip_storage_location_uuid = location["uuid"]

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
        resp = self.client.add_space(self._adjust_space_data(self.SPACES[self.dst]))
        assert resp.status_code == 201
        space = json.loads(resp.content)

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
        rp_location = json.loads(resp.content)

        # 3. Install replicator (not possible via API).
        rp_location = Location.objects.get(uuid=rp_location["uuid"])
        if self.use_registered_aip_storage_location:
            as_location = Location.objects.get(uuid=self.aip_storage_location_uuid)
        else:
            resp = self.client.get_locations(
                {
                    "pipeline_uuid": str(self.PIPELINE_UUID),
                    "purpose": Location.AIP_STORAGE,
                }
            )
            as_location_data = json.loads(resp.content)["objects"][0]
            as_location = Location.objects.get(uuid=as_location_data["uuid"])
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
        cp_location = json.loads(resp.content)["objects"][0]
        if self.use_registered_aip_storage_location:
            aip_storage_location_resource_uri = self.aip_storage_location_resource_uri
            aip_storage_location_path = self.aip_storage_location_path
        else:
            resp = self.client.get_locations(
                {
                    "pipeline_uuid": str(self.PIPELINE_UUID),
                    "purpose": Location.AIP_STORAGE,
                }
            )
            aip_storage_location = json.loads(resp.content)["objects"][0]
            aip_storage_location_resource_uri = aip_storage_location["resource_uri"]
            aip_storage_location_path = aip_storage_location["path"]

        resp = self.client.add_file(
            self.PACKAGE_UUID,
            {
                "uuid": str(self.PACKAGE_UUID),
                "origin_location": cp_location["resource_uri"],
                "origin_path": self.pkg_name,
                "current_location": aip_storage_location_resource_uri,
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

        aip = json.loads(resp.content)
        aip_id = self.PACKAGE_UUID.hex
        aip_path_parts = (
            [aip_storage_location_path]
            + [aip_id[i : i + 4] for i in range(0, len(aip_id), 4)]
            + [self.pkg_name]
        )
        aip_path = Path(*aip_path_parts)
        assert aip["uuid"] == str(self.PACKAGE_UUID)
        assert aip["current_full_path"] == str(aip_path)
        if (
            self.use_registered_aip_storage_location
            and self.src in self.OBJECT_STORAGE_PROTOCOLS
        ):
            stored_size = Package.objects.get(uuid=self.PACKAGE_UUID).size
            assert stored_size == get_size(self.pkg)
        else:
            assert get_size(aip_path) > 1

    def assert_stored(self) -> None:
        # We have two packages, the original and a replica.
        resp = self.client.get_files()
        files = json.loads(resp.content)
        assert files["meta"]["total_count"] == 2
        assert len(files["objects"]) == 2

        # Fixity checks.
        resp = self.client.check_fixity(files["objects"][0]["uuid"])
        assert resp.status_code == 200
        assert json.loads(resp.content)["success"] is True
        resp = self.client.check_fixity(files["objects"][1]["uuid"])
        assert resp.status_code == 200
        assert json.loads(resp.content)["success"] is True

        # We have a pointer file (not for uncompressed AIPs yet).
        if self.compressed:
            resp = self.client.get_pointer_file(self.PACKAGE_UUID)
            assert resp.status_code == 200


@pytest.mark.parametrize(
    "storage_scenario",
    [
        StorageScenario(
            src=Space.NFS, dst=Space.S3, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.NFS, dst=Space.S3, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.NFS, dst=Space.RCLONE, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.NFS, dst=Space.RCLONE, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.S3, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.S3, dst=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.RCLONE, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.RCLONE, dst=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.S3, dst=Space.S3, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.S3, dst=Space.S3, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.RCLONE, dst=Space.RCLONE, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.RCLONE,
            dst=Space.RCLONE,
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
    ],
)
@pytest.mark.django_db
def test_main(
    startup: None,
    storage_scenario: StorageScenario,
    admin_client: TestClient,
    working_directory_path: Path,
) -> None:
    storage_scenario.init(admin_client, working_directory_path)
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
        assert not json.loads(resp.content)["success"]

    def copy_fixture_to_aip_recovery_location(self) -> None:
        resp = self.client.get_locations(
            {"pipeline_uuid": str(self.PIPELINE_UUID), "purpose": Location.AIP_RECOVERY}
        )
        aip_recovery_location_path = Path(
            json.loads(resp.content)["objects"][0]["path"]
        )

        # Clear recovery location.
        shutil.rmtree(aip_recovery_location_path)
        aip_recovery_location_path.mkdir()

        self.copy_fixture(aip_recovery_location_path)

    def request_aip_recovery(self, data: Dict[str, Union[str, int]]) -> HttpResponse:
        return self.client.request_aip_recovery(self.PACKAGE_UUID, data)

    def approve_aip_recovery_request(self, event_id: int) -> HttpResponse:
        return self.client.approve_aip_recovery_request(event_id)

    def recover_aip(self) -> None:
        data: Dict[str, Union[str, int]] = {
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

        assert "Request approved: AIP restored." in resp.content.decode()

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
        assert json.loads(resp.content)["success"]

    def assert_recovered(self, tmp_path: Path) -> None:
        download_path = tmp_path / "download"

        resp = self.client.download_file(self.PACKAGE_UUID)

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
                src=Space.NFS, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
            ),
            False,
        ),
        (
            AIPRecoveryScenario(
                src=Space.NFS, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
            ),
            True,
        ),
        (
            AIPRecoveryScenario(
                src=Space.NFS, dst=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
            ),
            False,
        ),
        (
            AIPRecoveryScenario(
                src=Space.NFS, dst=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
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
    admin_client: TestClient,
    working_directory_path: Path,
    tmp_path: Path,
) -> None:
    scenario.init(admin_client, working_directory_path)
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
    admin_client: TestClient,
    working_directory_path: Path,
) -> None:
    # This represents an scenario where the user does not place the recovery
    # copy in the recovery location directory, creates the recovery request
    # and approves it.
    scenario = AIPRecoveryScenario(
        src=Space.NFS, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
    )
    scenario.init(admin_client, working_directory_path)
    scenario.store_aip()
    scenario.assert_stored()
    scenario.corrupt_package()

    data: Dict[str, Union[str, int]] = {
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

    content = resp.content.decode()
    assert "AIP restore failed: error accessing restore files" in content
    assert "Please contact an administrator or see logs for details" in content


class AIPDeletionScenario(StorageScenario):
    def delete_package(self, file_uuid: uuid.UUID, expected_protocol: str) -> str:
        data: Dict[str, Union[str, int]] = {
            "event_reason": "Delete please!",
            "pipeline": str(self.PIPELINE_UUID),
            "user_id": 1,
            "user_email": "user@example.com",
        }

        # Request package deletion through the public API.
        resp = self.client.request_aip_deletion(file_uuid, data)

        assert resp.status_code == 202
        assert Event.objects.count() == 1

        # Confirm the deletion request targets the package we are deleting.
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
        package_full_path = str(package.full_path)

        assert package.current_location.space.access_protocol == expected_protocol
        if expected_protocol not in self.OBJECT_STORAGE_PROTOCOLS:
            assert Path(package_full_path).exists()

        # Approve the deletion request through the admin-only review view.
        resp = self.client.approve_aip_deletion_request(event.id)
        content = resp.content.decode()

        assert resp.status_code == 200
        assert "Request approved: Package deleted successfully." in content

        # The package row is kept and marked deleted after successful deletion.
        package.refresh_from_db()

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
        assert package.status == Package.DELETED

        return package_full_path


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

    assert isinstance(createdate, str)

    return createdate


def current_storage_timestamp() -> datetime.datetime:
    return datetime.datetime.utcnow().replace(microsecond=0)


def parse_storage_timestamp(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")


def get_7z_version() -> str:
    return [
        line
        for line in subprocess.check_output(["7z"]).splitlines()
        if line.startswith(b"p7zip")
    ][0].decode("utf8")


def get_xml_elements_by_local_name(
    root: etree._Element, local_name: str
) -> List[etree._Element]:
    return [
        element
        for element in root.iter()
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == local_name
    ]


def get_child_text(element: etree._Element, child_name: str) -> str:
    children = get_xml_elements_by_local_name(element, child_name)

    assert len(children) == 1
    assert isinstance(children[0].text, str)

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
    admin_client: TestClient,
    working_directory_path: Path,
    storage_protocol: str,
    replication_protocol: str,
) -> None:
    # Store a compressed AIP in remote storage and create its replica.
    scenario = AIPDeletionScenario(
        src=storage_protocol,
        dst=replication_protocol,
        pkg=COMPRESSED_PACKAGE,
        compressed=True,
        use_registered_aip_storage_location=True,
    )
    scenario.init(admin_client, working_directory_path)
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
    missing_pointer_error = rf"Error reading file.*{re.escape(str(aip_pointer_path))}.*(No such file or directory|failed to load external entity)"
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
    expected_7z_version = get_7z_version()
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
    admin_client: TestClient,
    working_directory_path: Path,
    storage_protocol: str,
    replication_protocol: str,
) -> None:
    # Store a compressed AIP in remote storage and create its replica.
    scenario = AIPDeletionScenario(
        src=storage_protocol,
        dst=replication_protocol,
        pkg=COMPRESSED_PACKAGE,
        compressed=True,
        use_registered_aip_storage_location=True,
    )
    scenario.init(admin_client, working_directory_path)
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
