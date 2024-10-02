"""Integration testing.

This module tests Archivematica Storage Service in isolation. It does not
require Archivematica pipelines deployed.

Currently, the tests in this module are executed via Docker Compose. It may be
worth investigating a setup where pytest orchestrates Compose services instead.

Missing: encryption, multiple replicators, packages generated with older versions
of Archivematica, etc...
"""

import json
import os
import shutil
import tarfile
import uuid
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

import pytest
from common import utils
from django.http import HttpResponse
from django.test import Client as TestClient
from django.urls import reverse
from locations.models import Event
from locations.models import Location
from locations.models import Package
from locations.models import Space
from metsrw.plugins import premisrw

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

    def download_file(self, file_id: uuid.UUID) -> HttpResponse:
        return self.admin_client.get(f"/api/v2/file/{file_id}/download/")


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
    }

    def __init__(self, src: str, dst: str, pkg: Path, compressed: bool) -> None:
        self.src = src
        self.dst = dst
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
        for attr in ["path", "staging_path"]:
            if (
                (value := data.get(attr) is not None)
                and isinstance(value, str)
                and value.startswith("/var/archivematica/sharedDirectory")
            ):
                data[attr] = value.replace(
                    "/var/archivematica/sharedDirectory",
                    str(self.shared_directory_path),
                )
        return data

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
        resp = self.client.get_locations(
            {"pipeline_uuid": str(self.PIPELINE_UUID), "purpose": Location.AIP_STORAGE}
        )
        as_location = json.loads(resp.content)["objects"][0]
        rp_location = Location.objects.get(uuid=rp_location["uuid"])
        as_location = Location.objects.get(uuid=as_location["uuid"])
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
        cp_location = json.loads(resp.content)["objects"][0]

        resp = self.client.get_locations(
            {"pipeline_uuid": str(self.PIPELINE_UUID), "purpose": Location.AIP_STORAGE}
        )
        as_location = json.loads(resp.content)["objects"][0]

        resp = self.client.add_file(
            self.PACKAGE_UUID,
            {
                "uuid": str(self.PACKAGE_UUID),
                "origin_location": cp_location["resource_uri"],
                "origin_path": self.pkg_name,
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

        aip = json.loads(resp.content)
        aip_id = self.PACKAGE_UUID.hex
        aip_path_parts = (
            [as_location["path"]]
            + [aip_id[i : i + 4] for i in range(0, len(aip_id), 4)]
            + [self.pkg_name]
        )
        aip_path = Path(*aip_path_parts)
        assert aip["uuid"] == str(self.PACKAGE_UUID)
        assert aip["current_full_path"] == str(aip_path)
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
