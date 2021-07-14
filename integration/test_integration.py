# -*- coding: utf-8 -*-
"""Integration testing.

This module tests Archivematica Storage Service in isolation. It does not
require Archivematica pipelines deployed.

Currently, the tests in this module are executed via Docker Compose. It may be
worth investigating a setup where pytest orchestrates Compose services instead.

Missing: encryption, multiple replicators, packages generated with older versions
of Archivematica, etc...
"""
from __future__ import unicode_literals

import json
import shutil
import os

import pytest

from metsrw.plugins import premisrw
from locations.models import Location, Package, Space

try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"

COMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513054116-5658e603-277b-4292-9b58-20bf261c8f88.7z"
)
UNCOMPRESSED_PACKAGE = (
    FIXTURES_DIR / "20200513060703-828c44bb-e631-4137-8638-bda4434218dc"
)


class Client(object):
    """Slim API client."""

    def __init__(self, admin_client):
        self.admin_client = admin_client

    def add_space(self, data):
        return self.admin_client.post(
            "/api/v2/space/", json.dumps(data), content_type="application/json"
        )

    def add_pipeline(self, data):
        return self.admin_client.post(
            "/api/v2/pipeline/", json.dumps(data), content_type="application/json"
        )

    def get_pipelines(self, data):
        return self.admin_client.get("/api/v2/pipeline/", data)

    def add_location(self, data):
        return self.admin_client.post(
            "/api/v2/location/", json.dumps(data), content_type="application/json"
        )

    def set_location(self, location_id, data):
        return self.admin_client.post(
            "/api/v2/location/{}/".format(location_id),
            json.dumps(data),
            content_type="application/json",
        )

    def get_locations(self, data):
        return self.admin_client.get("/api/v2/location/", data)

    def add_file(self, file_id, data):
        return self.admin_client.put(
            "/api/v2/file/{}/".format(file_id),
            json.dumps(data),
            content_type="application/json",
        )

    def get_files(self):
        return self.admin_client.get("/api/v2/file/")

    def get_pointer_file(self, file_id):
        return self.admin_client.get("/api/v2/file/{}/pointer_file/".format(file_id))

    def check_fixity(self, file_id):
        return self.admin_client.get("/api/v2/file/{}/check_fixity/".format(file_id))


@pytest.fixture()
def client(admin_client, scope="session"):
    return Client(admin_client)


@pytest.fixture()
def startup(scope="function"):
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

    startup()  # TODO: get rid of this!


def get_size(path):
    if isinstance(path, Path):
        path = str(path)
    if os.path.isfile(path):
        return os.path.getsize(path)
    size = 0
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            size += os.path.getsize(file_path)
    return size


class StorageScenario(object):
    """Storage test scenario."""

    PIPELINE_UUID = "00000b87-1655-4b7e-bbf8-344b317da334"
    PACKAGE_UUID = "5658e603-277b-4292-9b58-20bf261c8f88"

    SPACES = {
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

    def __init__(self, src, dst, pkg, compressed):
        self.src = src
        self.dst = dst
        self.pkg = pkg
        self.compressed = compressed
        self.client = None

    def init(self, admin_client):
        self.client = Client(admin_client)
        self.register_pipeline()
        self.register_aip_storage_location()
        self.register_aip_storage_replicator()
        self.copy_fixture()

    def register_pipeline(self):
        resp = self.client.add_pipeline(
            {
                "uuid": self.PIPELINE_UUID,
                "description": "Beefy pipeline",
                "create_default_locations": True,
                "shared_path": "/var/archivematica/sharedDirectory",
                "remote_name": "http://127.0.0.1:65534",
                "api_username": "test",
                "api_key": "test",
            }
        )
        assert resp.status_code == 201

    def register_aip_storage_location(self):
        """Register AIP Storage location."""

        # 1. Remove existing AIP Storage location.
        Location.objects.filter(
            pipeline__uuid=[self.PIPELINE_UUID], purpose=Location.AIP_STORAGE
        ).delete()

        # 2. Add space.
        resp = self.client.add_space(self.SPACES[self.src])
        assert resp.status_code == 201
        space = json.loads(resp.content)

        # 3. Add location.
        resp = self.client.add_location(
            {
                "relative_path": "aips",
                "staging_path": "",
                "purpose": Location.AIP_STORAGE,
                "space": space["resource_uri"],
                "pipeline": ["/api/v2/pipeline/{}/".format(self.PIPELINE_UUID)],
            }
        )
        assert resp.status_code == 201

    def get_compression_event(self):
        return tuple(
            [
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
            ]
        )

    def get_agent(self):
        return tuple(
            [
                "agent",
                premisrw.PREMIS_3_0_META,
                (
                    "agent_identifier",
                    ("agent_identifier_type", "foobar"),
                    ("agent_identifier_value", "foobar"),
                ),
                ("agent_name", "foobar"),
                ("agent_type", "foobar"),
            ]
        )

    def register_aip_storage_replicator(self):
        """Register AIP Storage replicator."""

        # 1. Add space.
        resp = self.client.add_space(self.SPACES[self.dst])
        assert resp.status_code == 201
        space = json.loads(resp.content)

        # 2. Add replicator location.
        resp = self.client.add_location(
            {
                "relative_path": "aips",
                "staging_path": "",
                "purpose": Location.REPLICATOR,
                "space": space["resource_uri"],
                "pipeline": ["/api/v2/pipeline/{}/".format(self.PIPELINE_UUID)],
            }
        )
        assert resp.status_code == 201
        rp_location = json.loads(resp.content)

        # 3. Install replicator (not possible via API).
        resp = self.client.get_locations(
            {"pipeline_uuid": self.PIPELINE_UUID, "purpose": Location.AIP_STORAGE}
        )
        as_location = json.loads(resp.content)["objects"][0]
        rp_location = Location.objects.get(uuid=rp_location["uuid"])
        as_location = Location.objects.get(uuid=as_location["uuid"])
        as_location.replicators.add(rp_location)
        assert (
            Location.objects.get(uuid=as_location.uuid).replicators.all().count() == 1
        )

    def copy_fixture(self):
        cp_location_path = Path("/var/archivematica/sharedDirectory")
        if self.pkg.is_dir():
            dst = cp_location_path / self.pkg.name
            if not dst.exists():
                shutil.copytree(str(FIXTURES_DIR / self.pkg), str(dst))
            assert dst.is_dir()
        else:
            shutil.copy(str(FIXTURES_DIR / self.pkg), str(cp_location_path))
            assert (cp_location_path / self.pkg).is_file()

    def store_aip(self):
        resp = self.client.get_locations(
            {
                "pipeline_uuid": self.PIPELINE_UUID,
                "purpose": Location.CURRENTLY_PROCESSING,
            }
        )
        cp_location = json.loads(resp.content)["objects"][0]

        resp = self.client.get_locations(
            {"pipeline_uuid": self.PIPELINE_UUID, "purpose": Location.AIP_STORAGE}
        )
        as_location = json.loads(resp.content)["objects"][0]

        resp = self.client.add_file(
            self.PACKAGE_UUID,
            {
                "uuid": self.PACKAGE_UUID,
                "origin_location": cp_location["resource_uri"],
                "origin_path": self.pkg.name,
                "current_location": as_location["resource_uri"],
                "current_path": self.pkg.name,
                "size": get_size(str(self.pkg)),
                "package_type": Package.AIP,
                "aip_subtype": "Archival Information Package",
                "origin_pipeline": "/api/v2/pipeline/{}/".format(self.PIPELINE_UUID),
                "events": [self.get_compression_event()],
                "agents": [self.get_agent()],
            },
        )
        assert resp.status_code == 201

        aip = json.loads(resp.content)
        aip_id = self.PACKAGE_UUID.replace("-", "")
        aip_path = (
            [as_location["path"]]
            + [aip_id[i : i + 4] for i in range(0, len(aip_id), 4)]
            + [self.pkg.name]
        )
        aip_path = Path(*aip_path)
        assert aip["uuid"] == self.PACKAGE_UUID
        assert aip["current_full_path"] == str(aip_path)
        assert get_size(aip_path) > 1

    def assert_stored(self):
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
            src=Space.S3, dst=Space.NFS, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.S3, dst=Space.NFS, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
        StorageScenario(
            src=Space.S3, dst=Space.S3, pkg=COMPRESSED_PACKAGE, compressed=True
        ),
        StorageScenario(
            src=Space.S3, dst=Space.S3, pkg=UNCOMPRESSED_PACKAGE, compressed=False
        ),
    ],
    ids=[
        "nfs_to_s3_compressed",
        "nfs_to_s3_uncompressed",
        "s3_to_nfs_compressed",
        "s3_to_nfs_uncompressed",
        "s3_to_s3_compressed",
        "s3_to_s3_uncompressed",
    ],
)
@pytest.mark.django_db(transaction=True)
def test_main(startup, storage_scenario, admin_client):
    storage_scenario.init(admin_client)
    storage_scenario.store_aip()
    storage_scenario.assert_stored()
