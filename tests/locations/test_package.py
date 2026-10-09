from __future__ import annotations

import datetime
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
from collections import namedtuple
from typing import TYPE_CHECKING
from unittest import mock

import bagit
import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.common import utils
from archivematica.storage_service.common.compression import CommandLineArchiver
from archivematica.storage_service.common.compression import override_archiver
from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.arkivum import Arkivum
from archivematica.storage_service.locations.models.gpg import GPG
from archivematica.storage_service.locations.models.package import _extract_rein_aip
from archivematica.storage_service.locations.models.replica_staging import (
    OfflineReplicaStaging,
)
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import SpaceFactory

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

TEST_CHECKSUM_HASHDIGEST = (
    "810ff2fb242a5dee4220f2cb0e6a519891fb67f2f828a6cab4ef8894633b1f50"
)


def _test_checksum():
    checksum = hashlib.new("sha256")
    checksum.update(b"testdata")
    return checksum


def recursive_file_count(target_dir):
    """Return count of files in directory based on recursive walk."""
    return sum(len(files) for _, _, files in os.walk(target_dir))


def recursive_dir_count(target_dir):
    """Return count of dirs in directory based on recursive walk."""
    return sum(len(dirs) for _, dirs, _ in os.walk(target_dir))


def mock_v():
    """Return mock namedtuple with attributes needed to store AIP."""
    V = namedtuple(
        "V",
        [
            "src_space",
            "dest_space",
            "should_have_pointer",
            "pointer_file_src",
            "pointer_file_dst",
            "already_generated_ptr_exists",
        ],
    )
    space = models.Space.objects.get(uuid="7d20c992-bc92-4f92-a794-7161ff2cc08b")
    return V(
        src_space=space,
        dest_space=space,
        should_have_pointer=False,
        pointer_file_src=None,
        pointer_file_dst=None,
        already_generated_ptr_exists=False,
    )


def create_temporary_pointer(tmp_dir, path):
    """Create temporary copy of pointer file at path."""
    dst_dir = tempfile.mkdtemp(dir=tmp_dir)
    temp_path = os.path.join(dst_dir, "temp_pointer.xml")
    shutil.copy2(path, temp_path)
    return temp_path


def _relative_to_root(path: pathlib.Path) -> str:
    """The path of a directory relative to the root of the default space."""
    return str(path.relative_to(os.sep))


@pytest.fixture
def package(package: models.Package) -> models.Package:
    """The compressed AIP of the shared fixtures with the bag of the fixtures as
    its archive, replacing the shared fixture for the whole module.
    """
    shutil.copy(FIXTURES_DIR / "working_bag.zip", package.full_path)

    return package


# The fixtures below point the default layout at the bags of the fixtures
# directory as its AIP storage and at the temporary directory for what the
# tests write.


@pytest.fixture
def default_space(default_space: models.Space, tmp_path: pathlib.Path) -> models.Space:
    """The default space, staging in the temporary directory."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    default_space.staging_path = str(staging_dir)
    default_space.save()

    return default_space


@pytest.fixture
def default_ss_internal(
    default_ss_internal: models.Location, tmp_path: pathlib.Path
) -> models.Location:
    """The internal location of the Storage Service, in the temporary
    directory.
    """
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir()
    default_ss_internal.relative_path = _relative_to_root(internal_dir)
    default_ss_internal.save()

    return default_ss_internal


@pytest.fixture
def testing_aip_storage(testing_aip_storage: models.Location) -> models.Location:
    """The AIP storage location pointed at the fixtures directory, where the
    bags of its packages are.
    """
    testing_aip_storage.relative_path = _relative_to_root(FIXTURES_DIR)
    testing_aip_storage.save()

    return testing_aip_storage


@pytest.fixture
def arkivum(arkivum: Arkivum) -> Arkivum:
    """The Arkivum space pointed at the fixtures directory, where the bags of
    its packages are.
    """
    arkivum.space.path = str(FIXTURES_DIR)
    arkivum.space.save()

    return arkivum


def _create_replicator(
    make_location: LocationFactory,
    location: models.Location,
    replication_dir: pathlib.Path,
    space: models.Space | None = None,
) -> models.Location:
    """Create a replicator of the location in the replication directory of
    the space, the location's own unless another is given.
    """
    replication_dir.mkdir()
    result = make_location(
        space or location.space,
        models.Location.REPLICATOR,
        relative_path=_relative_to_root(replication_dir),
    )
    location.replicators.add(result)

    return result


@pytest.fixture
def replicator(
    make_location: LocationFactory,
    testing_aip_storage: models.Location,
    tmp_path: pathlib.Path,
) -> models.Location:
    """A replicator of the AIP storage location, in the temporary directory."""
    return _create_replicator(
        make_location, testing_aip_storage, tmp_path / "replication"
    )


@pytest.fixture
def offline_replicator(
    make_space: SpaceFactory,
    make_location: LocationFactory,
    testing_aip_storage: models.Location,
    tmp_path: pathlib.Path,
) -> models.Location:
    """A replicator of the AIP storage location in an offline replica staging
    space, which stages in the temporary directory.
    """
    staging_dir = tmp_path / "offline"
    staging_dir.mkdir()
    space = make_space(
        access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
        path="/",
        staging_path=str(staging_dir),
    )
    OfflineReplicaStaging.objects.create(space=space)

    return _create_replicator(
        make_location, testing_aip_storage, tmp_path / "replication", space=space
    )


def test_model_delete_from_storage(sevenzipped_bag: models.Package) -> None:
    """Test that the Space delete method is called once for the
    deletion of an AIP from the storage service.
    """

    # Package that exists in the storage service.
    package = sevenzipped_bag

    # Assert that is hasn't been deleted already.
    assert package.status == "Uploaded"

    # Using our context manager make sure that the deletion happens
    # once for our source object.
    with mock.patch(
        "archivematica.storage_service.locations.models.Space.delete_path"
    ) as mocked_delete:
        package.delete_from_storage()
        mocked_delete.assert_called()

    # Ensure that location properties are updated reflecting the
    # size remaining.
    assert package.current_location.used == -package.size
    assert package.current_location.space.used == -package.size

    # Ensure that the package status is accurately updated to
    # DELETED.
    assert package.status == models.Package.DELETED


def test_model_delete_from_storage_and_replicas(
    replicated_package: models.Package,
) -> None:
    """Test that Space delete method is called three times for a
    package with two replicas. Once for the original package. Twice
    for the two replicas.
    """

    # Package with two replicas in the storage service.
    package = replicated_package

    # Given our test object, make sure the replicas have equivalent
    # status.
    replicas = package._find_replicas()
    assert package.status == models.Package.UPLOADED
    assert replicas[0].status == models.Package.UPLOADED
    assert replicas[1].status == models.Package.UPLOADED

    # Using our context manager make sure that the deletion can be
    # measured three times per our test parameters.
    with mock.patch(
        "archivematica.storage_service.locations.models.Space.delete_path"
    ) as mocked_delete:
        package.delete_from_storage()
        mocked_delete.assert_called()
        assert mocked_delete.call_count == 3

    # Ensure locations sizes are updated to reflect the size
    # remaining.
    assert package.current_location.used == -package.size
    assert package.current_location.space.used == -package.size

    # Ensure that the replicas and the original package have an
    # updated status of DELETED.
    replicas = package._find_replicas(status=models.Package.DELETED)
    assert package.status == models.Package.DELETED
    assert replicas[0].status == models.Package.DELETED
    assert replicas[1].status == models.Package.DELETED


def test_model_delete_failure_with_replicas(
    replicated_package: models.Package,
) -> None:
    """If the deletion of an original package doesn't succeed for
    some reason, we don't want to proceed to delete the replicas
    associated with that package. That should be done as an
    independent action by the user, otherwise they are paired
    activities.
    """

    # Package with two replicas in the storage service.
    package = replicated_package

    # Store our original space and location values to test after
    # our "failed" delete call.
    original_location_used = package.current_location.used
    original_space_used = package.current_location.space.used

    # Using our context manager attempt to delete our package but
    # make sure the correct behavior occurs when an exception is
    # raised, e.g. NotImplementedError for a space without a storage
    # service managed deletion capability.
    with mock.patch(
        "archivematica.storage_service.locations.models.Space.delete_path",
        side_effect=NotImplementedError,
    ) as mocked_delete:
        package.delete_from_storage()
        mocked_delete.assert_called()
        assert mocked_delete.call_count == 1

    # Ensure locations sizes are the same as they were because no
    # deletion happened.
    assert package.current_location.used == original_location_used
    assert package.current_location.space.used == original_space_used

    # Ensure that the replicas and the original package have not
    # seen their status updated.
    replicas = package._find_replicas()
    assert package.status == models.Package.UPLOADED
    assert replicas[0].status == models.Package.UPLOADED
    assert replicas[1].status == models.Package.UPLOADED


def test_view_package_delete(
    client: Client, api_user: User, images_transfer: models.Package
) -> None:
    client.force_login(api_user)
    url = reverse(
        "locations:package_delete", args=["00000000-0000-0000-0000-000000000000"]
    )

    # It does only accept POST, i.e. GET returns a 405
    response = client.get(url, follow=True)
    assert response.status_code == 405

    # It returns a 404 when the UUID is unknown
    response = client.post(url, follow=True)
    assert response.status_code == 404

    def verify_redirect_message(
        response: _MonkeyPatchedWSGIResponse, message: str
    ) -> None:
        assert response.status_code == 200
        assert response.redirect_chain == [("/packages/", 302)]
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert str(messages[0]) == message

    # It returns an "error" message when the package type is not allowed.
    url = reverse("locations:package_delete", args=[images_transfer.uuid])
    response = client.post(url, follow=True)
    verify_redirect_message(
        response, "Package of type Transfer cannot be deleted directly"
    )

    # It returns a "success" message when the package was deleted
    # successfully and updates its status
    models.Package.objects.filter(uuid=images_transfer.uuid).update(
        package_type=models.Package.DIP
    )
    response = client.post(url, follow=True)
    verify_redirect_message(response, "Package deleted successfully!")
    assert (
        models.Package.objects.get(uuid=images_transfer.uuid).status
        == models.Package.DELETED
    )

    # It returns an "error" message when the package could not be deleted
    # and the underlying code raised an exception.
    with mock.patch(
        "archivematica.storage_service.locations.models.Package.delete_from_storage",
        side_effect=ValueError,
    ):
        response = client.post(url, follow=True)
        verify_redirect_message(
            response,
            "Package deletion failed. Please contact an"
            " administrator or see logs for details.",
        )

    # It returns an "error" message when the package could not be deleted.
    with mock.patch(
        "archivematica.storage_service.locations.models.Package.delete_from_storage",
        return_value=(False, "Something went wrong"),
    ):
        response = client.post(url, follow=True)
        verify_redirect_message(
            response,
            "Package deletion failed. Please contact an"
            " administrator or see logs for details.",
        )


def test_parsing_mets_data(images_transfer: models.Package) -> None:
    mets_data = images_transfer._parse_mets(prefix=str(FIXTURES_DIR))
    assert mets_data["transfer_uuid"] == "de1b31fa-97dd-48e0-8417-03be78359531"
    assert mets_data["dashboard_uuid"] == "23879cf0-a21a-40ee-bc50-357186746d15"
    assert mets_data["creation_date"] == "2015-02-21T01:55:08"
    assert len(mets_data["files"]) == 11
    # This file's name was changed ("filename change"), so check to see if
    # the correct name is used.
    assert [
        item["path"]
        for item in mets_data["files"]
        if item["file_uuid"] == "742f10b0-768a-4158-b255-94847a97c465"
    ] == [
        "images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg"
    ]


def test_files_are_added_to_database(images_transfer: models.Package) -> None:
    images_transfer.index_file_data_from_transfer_mets(prefix=str(FIXTURES_DIR))
    assert (
        images_transfer.file_set.count() == 12
    )  # 11 from this METS, plus the one the fixture is already assigned
    assert (
        images_transfer.file_set.get(
            name="images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg"
        ).source_id
        == "742f10b0-768a-4158-b255-94847a97c465"
    )


@pytest.fixture
def package_being_stored(
    one_file_transfer: models.Package,
    default_ss_internal: models.Location,
    default_currently_processing: models.Location,
) -> models.Package:
    """The transfer about to be stored as an AIP: it comes from the internal
    location of the Storage Service and is being processed.
    """
    one_file_transfer.origin_path = "origin/path"
    one_file_transfer.origin_location = default_ss_internal
    one_file_transfer.current_location = default_currently_processing
    one_file_transfer.save()

    return one_file_transfer


def _store_aip_to_uploaded(
    package: models.Package, related_package: models.Package
) -> None:
    """Store the package as the AIP of the related transfer."""
    package._store_aip_to_uploaded(mock_v(), str(related_package.uuid))


@mock.patch(
    "archivematica.storage_service.common.utils.generate_checksum",
    return_value=_test_checksum(),
)
def test_stored_checksum(
    generate_checksum: mock.MagicMock,
    package_being_stored: models.Package,
    empty_transfer: models.Package,
) -> None:
    package = package_being_stored
    assert package.checksum is None

    with mock.patch("archivematica.storage_service.locations.models.Space.posix_move"):
        with mock.patch(
            "archivematica.storage_service.locations.models.Package._update_quotas"
        ):
            _store_aip_to_uploaded(package, empty_transfer)
            assert package.checksum and package.checksum == TEST_CHECKSUM_HASHDIGEST
            assert (
                package.checksum_algorithm
                and package.checksum_algorithm
                == models.Package.DEFAULT_CHECKSUM_ALGORITHM
            )


@mock.patch("archivematica.storage_service.locations.models.Package._update_quotas")
@mock.patch(
    "archivematica.storage_service.locations.models.Space.move_to_storage_service"
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.post_move_to_storage_service"
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.move_from_storage_service"
)
@mock.patch(
    "archivematica.storage_service.common.utils.generate_checksum",
    return_value=_test_checksum(),
)
def test_stored_checksum_posix_exception(
    update_quotas: mock.MagicMock,
    move_to: mock.MagicMock,
    post_move: mock.MagicMock,
    move_from: mock.MagicMock,
    generate_checksum: mock.MagicMock,
    package_being_stored: models.Package,
    empty_transfer: models.Package,
) -> None:
    package = package_being_stored
    assert package.checksum is None

    with mock.patch(
        "archivematica.storage_service.locations.models.Space.posix_move"
    ) as posix_move:
        posix_move.side_effect = models.space.PosixMoveUnsupportedError
        _store_aip_to_uploaded(package, empty_transfer)
        assert package.checksum and package.checksum == TEST_CHECKSUM_HASHDIGEST
        assert (
            package.checksum_algorithm
            and package.checksum_algorithm == models.Package.DEFAULT_CHECKSUM_ALGORITHM
        )


@mock.patch(
    "archivematica.storage_service.common.utils.generate_checksum",
    return_value=_test_checksum(),
)
def test_stored_date(
    generate_checksum: mock.MagicMock,
    package_being_stored: models.Package,
    empty_transfer: models.Package,
) -> None:
    package = package_being_stored
    assert package.stored_date is None

    with mock.patch("archivematica.storage_service.locations.models.Space.posix_move"):
        with mock.patch(
            "archivematica.storage_service.locations.models.Package._update_quotas"
        ):
            _store_aip_to_uploaded(package, empty_transfer)
            assert package.stored_date and isinstance(
                package.stored_date, datetime.datetime
            )


@mock.patch("archivematica.storage_service.locations.models.Package._update_quotas")
@mock.patch(
    "archivematica.storage_service.locations.models.Space.move_to_storage_service"
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.post_move_to_storage_service"
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.move_from_storage_service"
)
@mock.patch(
    "archivematica.storage_service.common.utils.generate_checksum",
    return_value=_test_checksum(),
)
def test_stored_date_posix_exception(
    update_quotas: mock.MagicMock,
    move_to: mock.MagicMock,
    post_move: mock.MagicMock,
    move_from: mock.MagicMock,
    generate_checksum: mock.MagicMock,
    package_being_stored: models.Package,
    empty_transfer: models.Package,
) -> None:
    package = package_being_stored
    assert package.stored_date is None

    with mock.patch(
        "archivematica.storage_service.locations.models.Space.posix_move"
    ) as posix_move:
        posix_move.side_effect = models.space.PosixMoveUnsupportedError
        _store_aip_to_uploaded(package, empty_transfer)
        assert package.stored_date and isinstance(
            package.stored_date, datetime.datetime
        )


def test_fixity_success(working_bag: models.Package) -> None:
    """
    It should return success.
    It should return no errors.
    It should have an empty message.
    """
    success, failures, message, timestamp = working_bag.check_fixity()
    assert success is True
    assert failures == []
    assert message == ""
    assert timestamp is None


def test_fixity_failure(broken_bag: models.Package) -> None:
    """
    It should return error.
    It should return a list of errors.
    It should have an error message.
    """
    success, failures, message, timestamp = broken_bag.check_fixity()
    assert success is False
    assert len(failures) == 1
    assert isinstance(failures[0], bagit.FileMissing)
    assert message == "Bag is incomplete"
    assert timestamp is None


def test_fixity_package_type(empty_transfer: models.Package) -> None:
    """It should only fixity bags."""
    success, failures, message, timestamp = empty_transfer.check_fixity()
    assert success is None
    assert failures == []
    assert "package is not a bag" in message
    assert timestamp is None


def test_fixity_success_package_checksum(working_bag: models.Package) -> None:
    """
    It should return success.
    It should return no errors.
    It should have an empty message.
    """
    # SHA-256 hash for working_bag's tagmanifest Bag file.
    working_bag.checksum = (
        "1e8096a2bba10d7a70689163374e21e671d0fcf917a78f88ef299fcd3dff5368"
    )
    working_bag.save()
    success, failures, message, timestamp = working_bag.check_fixity()
    assert success is True
    assert failures == []
    assert message == ""
    assert timestamp is None


def test_fixity_success_compressed_package_checksum(
    sevenzipped_bag: models.Package, default_ss_internal: models.Location
) -> None:
    """
    It should return success.
    It should return no errors.
    It should have an empty message.
    """
    sevenzipped_bag.checksum = (
        "aff81b3a69fe9e44a36cdfd1b7b2068f33066755c781eff95f95eb9147808c30"
    )
    sevenzipped_bag.save()
    success, failures, message, timestamp = sevenzipped_bag.check_fixity()
    assert success is True
    assert failures == []
    assert message == ""
    assert timestamp is None


def test_fixity_failure_package_checksum(broken_bag: models.Package) -> None:
    """
    It should return error.
    It should return a list of errors.
    It should have an error message.
    """
    broken_bag.checksum = "incorrect"
    broken_bag.save()
    success, failures, message, timestamp = broken_bag.check_fixity()
    assert success is False
    assert len(failures) == 1
    assert "Expected package checksum" in failures[0]
    assert message == "Incorrect package checksum"
    assert timestamp is None


@pytest.fixture
def arkivum_checked_package(
    arkivum_uncompressed_package: models.Package,
) -> models.Package:
    """The uncompressed package of the Arkivum space, whose fixity Arkivum is
    checking.
    """
    arkivum_uncompressed_package.misc_attributes.update(
        {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
    )
    arkivum_uncompressed_package.save()

    return arkivum_uncompressed_package


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "status": "Scheduled",
                },
            }
        )
    ],
)
def test_fixity_scheduled_arkivum(
    requests_get: mock.MagicMock, arkivum_checked_package: models.Package
) -> None:
    """It should return success of None."""
    success, failures, message, timestamp = arkivum_checked_package.check_fixity(
        force_local=False
    )
    assert success is None
    assert message == "Arkivum fixity check in progress"
    assert failures == []
    assert timestamp is None


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "processed": 18,
                    "replicationState": "amber",
                    "fixityLastChecked": "2015-11-24",
                    "replicationStates": {"amber": 18},
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "passed": "18",
                    "status": "Completed",
                },
            }
        )
    ],
)
def test_fixity_amber_arkivum(
    requests_get: mock.MagicMock, arkivum_checked_package: models.Package
) -> None:
    """It should return success of None."""
    success, failures, message, timestamp = arkivum_checked_package.check_fixity(
        force_local=False
    )
    assert success is None
    assert message == "Arkivum fixity check in progress"
    assert failures == []
    assert timestamp == "2015-11-24T00:00:00"


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "processed": 18,
                    "replicationState": "green",
                    "fixityLastChecked": "2015-11-24",
                    "replicationStates": {"green": 18},
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "passed": "18",
                    "status": "Completed",
                },
            }
        )
    ],
)
def test_fixity_success_arkivum(
    requests_get: mock.MagicMock, arkivum_checked_package: models.Package
) -> None:
    """It should return Arkivum's successful fixity not generate its own."""
    success, failures, message, timestamp = arkivum_checked_package.check_fixity(
        force_local=False
    )
    assert success is True
    assert message == ""
    assert failures == []
    assert timestamp == "2015-11-24T00:00:00"


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "failures": [
                        {
                            "filepath": "data/test/test1.txt",
                            "reason": "Initial verification failed",
                        },
                        {
                            "reason": "Initial verification failed",
                            "filepath": "manifest-md5.txt",
                        },
                    ],
                    "id": "059b7285-dfd7-45f9-be31-f6609435b6ed",
                    "status": "Failed",
                },
            }
        )
    ],
)
def test_fixity_failure_arkivum(
    requests_get: mock.MagicMock, arkivum_checked_package: models.Package
) -> None:
    """It should return success of False from Arkivum."""
    success, failures, message, timestamp = arkivum_checked_package.check_fixity(
        force_local=False
    )
    assert success is False
    assert message == "invalid bag"
    assert len(failures) == 2
    assert {
        "filepath": "data/test/test1.txt",
        "reason": "Initial verification failed",
    } in failures
    assert {
        "reason": "Initial verification failed",
        "filepath": "manifest-md5.txt",
    } in failures
    assert timestamp is None


def test_fixity_force_local(arkivum_uncompressed_package: models.Package) -> None:
    """It should do checksum locally if required."""
    success, failures, message, timestamp = arkivum_uncompressed_package.check_fixity(
        force_local=True
    )
    assert success is True
    assert failures == []
    assert message == ""
    assert timestamp is None


def test_extract_file_aip_from_uncompressed_aip(
    working_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should return an aip"""
    basedir = working_bag.get_base_directory()
    output_path, extract_path = working_bag.extract_file(extract_path=str(tmp_path))
    assert output_path == os.path.join(tmp_path, basedir)
    assert os.path.join(output_path, "manifest-md5.txt")


def test_extract_file_file_from_uncompressed_aip(
    working_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should return a single file from an uncompressed aip"""
    basedir = working_bag.get_base_directory()
    output_path, extract_path = working_bag.extract_file(
        relative_path="working_bag/manifest-md5.txt", extract_path=str(tmp_path)
    )
    assert output_path == os.path.join(tmp_path, basedir, "manifest-md5.txt")
    assert os.path.isfile(output_path)


def test_extract_file_nested_file_from_uncompressed_aip(
    working_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should return a single file from an uncompressed aip (with nested path)"""
    basedir = working_bag.get_base_directory()
    output_path, extract_path = working_bag.extract_file(
        relative_path="working_bag/data/test.txt", extract_path=str(tmp_path)
    )
    assert output_path == os.path.join(tmp_path, basedir, "data/test.txt")
    assert os.path.isfile(output_path)


def test_extract_file_file_from_compressed_aip(
    sevenzipped_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should return a single file from a 7zip compressed aip"""
    basedir = sevenzipped_bag.get_base_directory()
    output_path, extract_path = sevenzipped_bag.extract_file(
        relative_path="working_bag/manifest-md5.txt", extract_path=str(tmp_path)
    )
    assert output_path == os.path.join(extract_path, basedir, "manifest-md5.txt")
    assert os.path.isfile(output_path)


def test_extract_file_file_does_not_exist_compressed(
    sevenzipped_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should raise an error because the requested file does not exist"""
    with pytest.raises(Exception) as e_info:
        output_path, extract_path = sevenzipped_bag.extract_file(
            relative_path="working_bag/manifest-sha512.txt",
            extract_path=str(tmp_path),
        )
    assert e_info.value.args[0] == "Extraction error"


def test_extract_file_aip_from_compressed_aip(
    sevenzipped_bag: models.Package,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """It should return an aip"""
    basedir = sevenzipped_bag.get_base_directory()
    output_path, extract_path = sevenzipped_bag.extract_file(extract_path=str(tmp_path))
    assert output_path == os.path.join(tmp_path, basedir)
    assert os.path.join(output_path, "manifest-md5.txt")


@pytest.mark.usefixtures("callback_rows")
def test_run_post_store_callbacks_aip(tar_gz_package: models.Package) -> None:
    uuid = str(tar_gz_package.uuid)
    with mock.patch(
        "archivematica.storage_service.locations.models.Callback.execute"
    ) as mocked_execute:
        tar_gz_package.run_post_store_callbacks()
        # Only `post_store_aip` callbacks are executed
        assert mocked_execute.call_count == 1
        # Placeholders replaced in URI and body
        url = "http://consumer.com/api/v1/aip/%s/" % uuid
        body = '{"name": "tar_gz_package", "uuid": "%s"}' % uuid
        mocked_execute.assert_called_with(url, body)


@pytest.mark.usefixtures("callback_rows")
def test_run_post_store_callbacks_aip_tricky_name(
    tricky_7z_package: models.Package,
) -> None:
    uuid = str(tricky_7z_package.uuid)
    with mock.patch(
        "archivematica.storage_service.locations.models.Callback.execute"
    ) as mocked_execute:
        tricky_7z_package.run_post_store_callbacks()
        # Only `post_store_aip` callbacks are executed
        assert mocked_execute.call_count == 1
        # Placeholders replaced in URI and body
        url = "http://consumer.com/api/v1/aip/%s/" % uuid
        body = '{"name": "a.bz2.tricky.7z.package", "uuid": "%s"}' % uuid
        mocked_execute.assert_called_with(url, body)


@pytest.mark.usefixtures("callback_rows")
def test_run_post_store_callbacks_aic(working_bag: models.Package) -> None:
    working_bag.package_type = models.Package.AIC
    working_bag.save()
    with mock.patch(
        "archivematica.storage_service.locations.models.Callback.execute"
    ) as mocked_execute:
        working_bag.run_post_store_callbacks()
        # Only enabled callbacks are executed
        assert mocked_execute.call_count == 1


@pytest.mark.usefixtures("callback_rows")
def test_run_post_store_callbacks_dip(working_bag: models.Package) -> None:
    uuid = str(working_bag.uuid)
    working_bag.package_type = models.Package.DIP
    working_bag.save()
    with mock.patch(
        "archivematica.storage_service.locations.models.Callback.execute"
    ) as mocked_execute:
        working_bag.run_post_store_callbacks()
        # Placeholder is replaced by the UUID in URI and body
        url = "https://consumer.com/api/v1/dip/%s/stored" % uuid
        body = '{"download_url": "http://ss.com/api/v2/file/%s/download/"}' % uuid
        mocked_execute.assert_called_with(url, body)


def _expected_bagit_structure(
    replica: models.Package, replication_dir: str
) -> set[str]:
    """The paths of the files of the test bag once replicated into the
    replication directory.
    """
    bag_contents = [
        "tagmanifest-md5.txt",
        "bagit.txt",
        "manifest-md5.txt",
        "bag-info.txt",
        os.path.join("data", "test.txt"),
    ]
    expected_bag_path = os.path.join(
        replication_dir, utils.uuid_to_path(replica.uuid), "working_bag"
    )

    return {os.path.join(expected_bag_path, bag_path) for bag_path in bag_contents}


def _found_bagit_structure(replica: models.Package) -> set[str]:
    """The paths of the files found in the current location of the replica,
    so that we know structure is preserved accurately.
    """
    return {
        os.path.join(subdir, file_)
        for subdir, _, files in os.walk(replica.current_location.full_path)
        for file_ in files
    }


def test_replicate_aip_when_file(
    sevenzipped_bag: models.Package,
    replicator: models.Location,
    default_ss_internal: models.Location,
) -> None:
    """Ensure that a replica can be created and its resulting
    properties are consistent for one of Archivematica's file-like
    AIP package types, e.g. 7z.
    """
    aip = sevenzipped_bag
    assert aip.replicas.count() == 0
    aip.create_replicas()
    assert aip.replicas.count() == 1
    replica = aip.replicas.first()
    assert replica is not None
    assert replica.origin_pipeline == aip.origin_pipeline
    assert replica.replicas.count() == 0
    assert replica.stored_date and isinstance(replica.stored_date, datetime.datetime)
    package_name = "working_bag.7z"
    dest_dir = os.path.join(replicator.full_path, utils.uuid_to_path(replica.uuid))
    repl_file_path = os.path.join(dest_dir, package_name)
    assert package_name in os.listdir(dest_dir)
    assert os.path.isfile(repl_file_path)


def test_replicate_aip(
    working_bag: models.Package,
    replicator: models.Location,
    default_ss_internal: models.Location,
) -> None:
    """Ensure that a replica can be created and its resulting
    properties and folder structure are consistent for a regular,
    non-packed bag in Archivematica, e.g. Uncompressed and not 7z
    etc.
    """
    aip = working_bag
    assert aip.replicas.count() == 0
    aip.create_replicas()
    assert aip.replicas.count() == 1
    replica = aip.replicas.first()
    assert replica is not None
    assert replica.origin_pipeline == aip.origin_pipeline
    assert replica.replicas.count() == 0
    assert replica.stored_date and isinstance(replica.stored_date, datetime.datetime)
    assert _found_bagit_structure(replica) == _expected_bagit_structure(
        replica, replicator.full_path
    )


def test_replicate_aic(
    small_aic: models.Package,
    replicator: models.Location,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """Ensure that replication works for AICs as well as AIPs."""
    aic = small_aic
    assert aic.replicas.count() == 0

    pointer = create_temporary_pointer(
        tmp_path,
        os.path.join(FIXTURES_DIR, "pointer.4781e745-96bc-4b06-995c-ee59fddf856d.xml"),
    )
    with mock.patch.object(models.Package, "full_pointer_file_path", pointer):
        aic.create_replicas()
        assert aic.replicas.count() == 1
        replica = aic.replicas.first()
        assert replica is not None
        assert replica.origin_pipeline == aic.origin_pipeline
        assert replica.status == models.Package.UPLOADED
        assert replica.replicas.count() == 0


def test_replicate_aip_twice(
    make_location: LocationFactory,
    working_bag: models.Package,
    testing_aip_storage: models.Location,
    replicator: models.Location,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """Ensure that multiple replicas can be created and its
    resulting properties and folder structure are consistent for a
    regular, non-packed bag in Archivematica, e.g. Uncompressed and
    not 7z etc. Make sure the properties correctly indicate two
    replicas.
    """
    second_replicator = _create_replicator(
        make_location, testing_aip_storage, tmp_path / "second-replication"
    )
    aip = working_bag

    assert aip.replicas.count() == 0

    aip.create_replicas()

    assert aip.replicas.count() == 2
    first_replica = aip.replicas.first()
    last_replica = aip.replicas.last()
    assert first_replica is not None
    assert last_replica is not None
    assert first_replica != last_replica

    assert first_replica.replicas.count() == 0
    assert last_replica.replicas.count() == 0

    assert _found_bagit_structure(first_replica) == _expected_bagit_structure(
        first_replica, replicator.full_path
    )
    assert _found_bagit_structure(last_replica) == _expected_bagit_structure(
        last_replica, second_replicator.full_path
    )


@mock.patch("archivematica.storage_service.locations.models.gpg._gpg_encrypt")
def test_replicate_aip_gpg_encrypted(
    mock_encrypt: mock.MagicMock,
    make_space: SpaceFactory,
    make_location: LocationFactory,
    working_bag: models.Package,
    testing_aip_storage: models.Location,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """Ensure that a replica is created correctly for a replication
    space created with a GPG encryption and ensure that the calls
    made to correct it look correct and the replica's properties are
    consistent.
    """
    mock_encrypt.return_value = ("/a/fake/path", mock.Mock())

    gpg_dir = tmp_path / "gpg"
    gpg_dir.mkdir()
    gpg_space = make_space(
        access_protocol=models.Space.GPG, path="/", staging_path=str(gpg_dir)
    )
    GPG.objects.create(space=gpg_space)
    gpg_replicator = _create_replicator(
        make_location, testing_aip_storage, tmp_path / "replication", space=gpg_space
    )

    aip = working_bag
    assert aip.replicas.count() == 0
    aip.create_replicas()
    replica = aip.replicas.first()

    assert aip.replicas.count() == 1
    assert replica is not None
    assert mock_encrypt.call_args_list == [
        mock.call(os.path.join(replica.full_path, ""), "")
    ]
    assert _found_bagit_structure(replica) == _expected_bagit_structure(
        replica, gpg_replicator.full_path
    )


def test_replicate_aip_offline_staging_uncompressed(
    working_bag: models.Package,
    offline_replicator: models.Location,
    default_ss_internal: models.Location,
) -> None:
    """Ensure that a replica is created and stored correctly as a tarball."""
    staging_dir = offline_replicator.space.staging_path
    staging_files_count_initial = recursive_file_count(staging_dir)
    staging_dirs_count_initial = recursive_dir_count(staging_dir)

    aip = working_bag
    assert aip.replicas.count() == 0

    aip.create_replicas()
    replica = aip.replicas.first()

    assert aip.replicas.count() == 1
    assert replica is not None
    expected_replica_path = os.path.join(
        offline_replicator.full_path, "working_bag.tar"
    )
    assert os.path.exists(expected_replica_path)
    assert replica.current_path == expected_replica_path

    assert staging_files_count_initial == recursive_file_count(staging_dir)
    assert staging_dirs_count_initial == recursive_dir_count(staging_dir)


def test_replicate_aip_offline_staging_compressed(
    sevenzipped_bag: models.Package,
    offline_replicator: models.Location,
    default_ss_internal: models.Location,
) -> None:
    """Ensure that a replica is created and stored correctly as-is."""
    staging_dir = offline_replicator.space.staging_path
    staging_files_count_initial = recursive_file_count(staging_dir)
    staging_dirs_count_initial = recursive_dir_count(staging_dir)

    aip = sevenzipped_bag
    assert aip.replicas.count() == 0

    aip.create_replicas()
    replica = aip.replicas.first()

    assert aip.replicas.count() == 1
    assert replica is not None
    expected_replica_path = os.path.join(offline_replicator.full_path, "working_bag.7z")
    assert os.path.exists(expected_replica_path)
    assert replica.current_path == expected_replica_path

    assert staging_files_count_initial == recursive_file_count(staging_dir)
    assert staging_dirs_count_initial == recursive_dir_count(staging_dir)


def test_deletion_and_creation_of_replicas_compressed(
    replicated_packages: list[models.Package],
    replicator: models.Location,
    default_ss_internal: models.Location,
) -> None:
    """Ensure that when it is requested a replica be created, then
    existing replicas are checked for and deleted if necessary, e.g.
    during a reingest process. Ensure that a new replica is created
    in its place which reflects the original's updated structure.
    """
    aip, first_replica, second_replica, _ = replicated_packages
    old_replicas = {first_replica.uuid, second_replica.uuid}

    # Previous replicas for this package should be 2. Ensure that
    # is correct and ensure that status for both is UPLOADED.
    previous_replicas = models.Package.objects.filter(replicated_package=aip).all()
    uploaded_repl = [
        repl for repl in previous_replicas if repl.status == models.Package.UPLOADED
    ]
    assert len(set(uploaded_repl)) == len(set(previous_replicas)) == len(old_replicas)

    with mock.patch(
        "archivematica.storage_service.locations.models.Space.move_rsync"
    ) as _:
        aip.create_replicas()

    # The replication process in the storage service will create
    # only as many new replicas as there are enabled locations so
    # in this scenario we will see two existing replicas deleted
    # and one new replica created.
    all_replicas = models.Package.objects.filter(replicated_package=aip).all()
    uploaded_repl = [
        repl for repl in all_replicas if repl.status == models.Package.UPLOADED
    ]
    deleted_repl = [
        repl for repl in all_replicas if repl.status == models.Package.DELETED
    ]

    # Make sure our counts are correct, 3 total, 2 deleted, 1 new
    # (uploaded).
    assert len(set(all_replicas)) == 3
    assert len(set(deleted_repl)) == len(old_replicas)
    assert len(uploaded_repl) == 1

    # Make sure the previous replicas we expected to be deleted were
    # marked as deleted.
    assert {package.uuid for package in deleted_repl} == old_replicas

    # Finally make sure the database has given us a new UUID for the
    # new replica.
    assert uploaded_repl[0].uuid not in old_replicas


def _create_mutable_fixture_for_replication(
    tmp_path: pathlib.Path, package_name: str, files: list[str]
) -> str:
    """Create a mutable fixture to test replication updates
    file-level structures correctly during its replication routines
    and perform other more sophisticated testing.

    :param tmp_path: Temporary directory where the AIP store is created.
    :param package_name: Name of the package directory.
    :param files: A list of files to write into the package
        directory.
    :return: Location of what would be the AIPstore for storage
        service functions to find any packages we create here.
    """
    DATA_TO_WRITE = "data"
    tmp_dir = tempfile.mkdtemp(dir=tmp_path)
    aip_dir = os.path.join(tmp_dir, package_name)
    os.mkdir(aip_dir)
    for f in files:
        with open(os.path.join(aip_dir, f), "w") as test_file:
            test_file.write(DATA_TO_WRITE)
    return tmp_dir


def test_deletion_and_creation_of_replicas_uncompressed(
    working_bag: models.Package,
    testing_aip_storage: models.Location,
    replicator: models.Location,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """Ensure that an uncompressed package is created properly.
    Because replication seeks to also update the package we try
    adding new files, e.g. it could be through enabling
    normalization during partial-reingest. Through these tests we
    also verify some properties about those files which support the
    storage service's preservation functions.
    """
    PACKAGE = "working_bag"
    FILES = ["file_one", "file_two", "file_three"]

    # The AIP storage location is a mutable store of the temporary directory.
    new_aip_store = _create_mutable_fixture_for_replication(tmp_path, PACKAGE, FILES)
    testing_aip_storage.relative_path = _relative_to_root(pathlib.Path(new_aip_store))
    testing_aip_storage.save()

    original_dir = os.path.join(new_aip_store, PACKAGE)
    aip = working_bag

    # Make sure there is no existing date polluting the tests.
    assert aip.replicas.count() == 0

    # Create the replica and assert some properties about it and
    # the original AIP's relationships.
    aip.create_replicas()
    assert aip.replicas.count() == 1
    replica = aip.replicas.first()
    assert replica is not None
    assert replica.origin_pipeline == aip.origin_pipeline
    assert replica.replicas.count() == 0

    # Ensure that our first replication was created as expected.
    first_repl_uuid = replica.uuid
    first_expected_repl = os.path.join(
        replicator.full_path, utils.uuid_to_path(first_repl_uuid), PACKAGE
    )
    assert set(os.listdir(first_expected_repl)) == set(FILES)
    assert replica.status == models.Package.UPLOADED

    # Add some new data to our original package and create some
    # properties that we can then measure.
    FILE_TO_ADD = "new_normalization"
    DATA_TO_ADD = "new data"
    new_file = os.path.join(original_dir, FILE_TO_ADD)
    with open(new_file, "w") as normalize_example:
        normalize_example.write(DATA_TO_ADD)
    # Because we have a mutable store to play with, we can have
    # some more fun, so lets test preservation of dates during
    # replication.
    TEST_DATETIME = datetime.datetime(
        year=1970, month=1, day=1, hour=22, minute=13, second=0
    )
    DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
    DATE_STRING = "1970-01-01T22:13:00"
    mod_time = time.mktime(TEST_DATETIME.timetuple())
    os.utime(new_file, (mod_time, mod_time))

    # Create the replica and ensure the first one no-longer exists.
    aip.create_replicas()
    assert not os.path.isdir(first_expected_repl)

    # We're only creating a second version of a replica so last() is
    # available as a shortcut to get to it.
    replica = aip.replicas.last()
    assert replica is not None
    second_repl_uuid = replica.uuid
    second_expected_repl = os.path.join(
        replicator.full_path, utils.uuid_to_path(second_repl_uuid), PACKAGE
    )

    # Ensure the replicated directory structure is what we expect.
    assert set(os.listdir(second_expected_repl)) == set(FILES + [FILE_TO_ADD])

    # Make sure the replicated statuses are correct.
    first_replica = aip.replicas.first()
    last_replica = aip.replicas.last()
    assert first_replica is not None
    assert last_replica is not None
    assert first_replica.status == models.Package.DELETED
    assert last_replica.status == models.Package.UPLOADED

    new_replicated_file = os.path.join(second_expected_repl, FILE_TO_ADD)
    repl_file_timestamp = os.path.getmtime(new_replicated_file)

    # Ensure the timestamp is preserved.
    pretty_timestamp = datetime.datetime.fromtimestamp(repl_file_timestamp).strftime(
        DATE_FORMAT
    )
    assert pretty_timestamp == TEST_DATETIME.strftime(DATE_FORMAT)
    assert pretty_timestamp == DATE_STRING

    # Ensure data was copied as expected.
    assert os.path.getsize(new_replicated_file) == len(DATA_TO_ADD)


def test_clear_local_tempdirs(
    working_bag: models.Package,
    zipped_bag: models.Package,
    default_ss_internal: models.Location,
) -> None:
    """Ensure package's local tempdirs are deleted.

    Tempdirs associated with other packages should be retained.
    """
    aip1 = working_bag
    aip2 = zipped_bag

    def mock_fetch_local_path(package: models.Package) -> str:
        tempdir = tempfile.mkdtemp(dir=default_ss_internal.full_path)
        package.local_tempdirs.append(tempdir)
        return tempdir

    # Create temporary directories.
    tempdir_to_delete = mock_fetch_local_path(aip1)
    tempdir_to_retain = mock_fetch_local_path(aip2)
    assert os.path.exists(tempdir_to_delete)
    assert os.path.exists(tempdir_to_retain)
    assert len(aip1.local_tempdirs) == 1 and aip1.local_tempdirs[0] == tempdir_to_delete
    assert len(aip2.local_tempdirs) == 1 and aip2.local_tempdirs[0] == tempdir_to_retain

    # Remove temporary directories for first AIP.
    with mock.patch(
        "archivematica.storage_service.locations.models.package._get_ss_internal_full_path",
        return_value=default_ss_internal.full_path,
    ):
        aip1.clear_local_tempdirs()
    assert not os.path.exists(tempdir_to_delete)
    assert os.path.exists(tempdir_to_retain)
    assert len(aip1.local_tempdirs) == 0
    assert len(aip2.local_tempdirs) == 1 and aip2.local_tempdirs[0] == tempdir_to_retain


@pytest.fixture
def move_locations(
    make_space: SpaceFactory, make_location: LocationFactory, tmp_path: pathlib.Path
) -> tuple[models.Location, models.Location]:
    """Two AIP storage locations at the root of a space in the temporary
    directory, to move packages between.
    """
    space = make_space(path=str(tmp_path))
    source = make_location(
        space, models.Location.AIP_STORAGE, description="Primary AIP storage location"
    )
    destination = make_location(
        space,
        models.Location.AIP_STORAGE,
        description="Secondary AIP storage location",
    )

    return source, destination


def test_move_compressed_aip(
    make_package: PackageFactory,
    move_locations: tuple[models.Location, models.Location],
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    src_location, dst_location = move_locations
    _, pkg_path = tempfile.mkstemp(dir=tmp_path)
    pkg = make_package(src_location, os.path.basename(pkg_path))
    assert pkg.current_location == src_location

    pointer_path = create_temporary_pointer(
        tmp_path,
        os.path.join(FIXTURES_DIR, "pointer.4781e745-96bc-4b06-995c-ee59fddf856d.xml"),
    )
    with mock.patch.object(models.Package, "full_pointer_file_path", pointer_path):
        pkg.move(dst_location)

    assert pkg.current_location == dst_location


def test_move_uncompressed_aip(
    make_package: PackageFactory,
    move_locations: tuple[models.Location, models.Location],
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    src_location, dst_location = move_locations
    pkg_path = tempfile.mkdtemp(dir=tmp_path)
    pkg = make_package(src_location, os.path.basename(pkg_path))
    assert pkg.current_location == src_location

    pointer_path = None
    with mock.patch.object(models.Package, "full_pointer_file_path", pointer_path):
        pkg.move(dst_location)

    assert pkg.current_location == dst_location


# The following fixtures create the replicators of a space in the temporary
# directory.


def _create_replicator_of(
    make_location: LocationFactory,
    location: models.Location,
    name: str,
    **fields: object,
) -> models.Location:
    """Create a replicator of the location in a directory of its space."""
    result = make_location(
        location.space, models.Location.REPLICATOR, relative_path=name, **fields
    )
    pathlib.Path(result.full_path).mkdir()
    location.replicators.add(result)

    return result


@pytest.fixture
def enabled_replicator(
    make_location: LocationFactory, aip_storage_location: models.Location
) -> models.Location:
    return _create_replicator_of(
        make_location, aip_storage_location, "enabled-replication"
    )


@pytest.fixture
def disabled_replicator(
    make_location: LocationFactory, aip_storage_location: models.Location
) -> models.Location:
    return _create_replicator_of(
        make_location, aip_storage_location, "disabled-replication", enabled=False
    )


def test_create_replicas_uses_only_enabled_replicators(
    package: models.Package,
    enabled_replicator: models.Location,
    disabled_replicator: models.Location,
) -> None:
    with mock.patch.object(models.Package, "replicate", autospec=True) as replicate:
        package.create_replicas()

    replicate.assert_called_once_with(package, enabled_replicator)


def test_create_replicas_skips_disabled_replicator_when_uuid_requested(
    package: models.Package, disabled_replicator: models.Location
) -> None:
    with mock.patch.object(models.Package, "replicate", autospec=True) as replicate:
        package.create_replicas(replicator_uuid=disabled_replicator.uuid)

    replicate.assert_not_called()


@mock.patch(
    "archivematica.storage_service.common.utils.generate_checksum",
    return_value=mock.Mock(
        **{
            "hexdigest.return_value": "098f6bcd4621d373cade4e832627b4f9",
        }
    ),
)
def test_get_fixity_check_report_send_signals_verifies_failed_fixity_check(
    generate_checksum: mock.MagicMock,
    package: models.Package,
    ss_internal_location: models.Location,
) -> None:
    package.checksum = "098f6bcd4621d373cade4e832627b4f6"
    package.save()

    report, response = package.get_fixity_check_report_send_signals()

    assert response == {
        "success": False,
        "message": "Incorrect package checksum",
        "failures": {"files": {"missing": [], "changed": [], "untracked": []}},
        "timestamp": None,
    }


def _failing_archiver() -> CommandLineArchiver:
    """Return an archiver whose tools always fail."""

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(command), 1, "", "broken")

    return CommandLineArchiver(run=run)


def test_get_base_directory_raises_storage_exception_when_listing_fails(
    package: models.Package,
) -> None:
    with (
        override_archiver(_failing_archiver()),
        pytest.raises(models.StorageException, match="Error determining basename"),
    ):
        package.get_base_directory()


def test_compress_package_raises_storage_exception_when_the_tool_fails(
    package: models.Package, ss_internal_location: models.Location
) -> None:
    with (
        override_archiver(_failing_archiver()),
        pytest.raises(models.StorageException, match="Error compressing package"),
    ):
        package.compress_package(utils.COMPRESSION_TAR)


def _archiver_failing_to_extract(partial_output: pathlib.Path) -> CommandLineArchiver:
    """Return an archiver whose listing works but whose extraction fails half-way."""
    listing = '{"lsarContents": [{"XADFileName": "aip", "XADIsDirectory": 1}]}'

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[0] == "lsar":
            return subprocess.CompletedProcess(list(command), 0, listing, "")
        partial_output.mkdir(parents=True, exist_ok=True)
        (partial_output / "partial.txt").write_text("partial")
        return subprocess.CompletedProcess(list(command), 2, "", "Data error")

    return CommandLineArchiver(run=run)


def test_extract_rein_aip_raises_storage_exception_when_listing_fails(
    ss_internal_location: models.Location, tmp_path: pathlib.Path
) -> None:
    archive = tmp_path / "aip.7z"
    archive.write_bytes(b"not an archive")

    with (
        override_archiver(_failing_archiver()),
        pytest.raises(models.StorageException, match="Error extracting reingested AIP"),
    ):
        _extract_rein_aip(ss_internal_location, str(archive), utils.COMPRESSION_7Z_BZIP)

    assert archive.exists()


def test_extract_rein_aip_keeps_the_archive_when_extraction_fails(
    ss_internal_location: models.Location, tmp_path: pathlib.Path
) -> None:
    """The listing succeeds and the tool fails: the incoming archive is kept."""
    archive = tmp_path / "aip.7z"
    archive.write_bytes(b"not an archive")
    partial_output = pathlib.Path(ss_internal_location.full_path) / "aip"

    with (
        override_archiver(_archiver_failing_to_extract(partial_output)),
        pytest.raises(
            models.StorageException, match="exited with status 2: Data error"
        ),
    ):
        _extract_rein_aip(ss_internal_location, str(archive), utils.COMPRESSION_7Z_BZIP)

    assert archive.exists()
    # What the tool extracted before failing is left for the operator.
    assert (partial_output / "partial.txt").exists()


def test_extract_rein_aip_extracts_with_the_tool_of_the_compression(
    ss_internal_location: models.Location, tmp_path: pathlib.Path
) -> None:
    """The reingested AIP is extracted by the tool of its compression, not by
    detecting the format of the archive.
    """
    archive = tmp_path / "aip.7z"
    archive.write_bytes(b"archive")
    listing = '{"lsarContents": [{"XADFileName": "aip", "XADIsDirectory": 1}]}'
    commands: list[list[str]] = []

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[0] == "lsar":
            return subprocess.CompletedProcess(list(command), 0, listing, "")
        extracted = pathlib.Path(ss_internal_location.full_path) / "aip"
        extracted.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(list(command), 0, "", "")

    with override_archiver(CommandLineArchiver(run=run)):
        extracted = _extract_rein_aip(
            ss_internal_location, str(archive), utils.COMPRESSION_7Z_BZIP
        )

    assert extracted == os.path.join(ss_internal_location.full_path, "aip")
    assert [command[:2] for command in commands] == [["lsar", "-ja"], ["7z", "x"]]
    assert not archive.exists()


def test_compress_package_accepts_a_directory_with_a_trailing_slash(
    package: models.Package,
    ss_internal_location: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    """A trailing slash in extract_path must not change where the archive goes."""
    compressed_path, parent = package.compress_package(
        utils.COMPRESSION_TAR, extract_path=f"{tmp_path}/"
    )

    assert parent == f"{tmp_path}/"
    assert compressed_path == str(tmp_path / "working_bag.tar")
    assert os.path.isfile(compressed_path)


def test_extract_file_accepts_a_directory_with_a_trailing_slash(
    package: models.Package,
    ss_internal_location: models.Location,
    tmp_path: pathlib.Path,
) -> None:
    output_path, extract_path = package.extract_file(extract_path=f"{tmp_path}/")

    assert extract_path == f"{tmp_path}/"
    assert output_path == str(tmp_path / "working_bag")
    assert os.path.isfile(os.path.join(output_path, "manifest-md5.txt"))


# Integration of transfer reading and indexing. It uses ``tiny_transfer``, a
# small transfer part of fixtures/.


@pytest.fixture
def transfer_backlog_location(
    make_space: SpaceFactory, make_location: LocationFactory
) -> models.Location:
    """A transfer backlog location in a local filesystem space rooted at /."""
    return make_location(make_space(path="/"), models.Location.BACKLOG)


def _create_transfer_package(
    location: models.Location,
    tmp_path: pathlib.Path,
    fixture_dir: str,
    name: str,
    make_bagit: bool = False,
) -> models.Package:
    """Copy the fixture transfer into the temporary directory and return its
    package in the location.
    """
    src = os.path.join(FIXTURES_DIR, fixture_dir)
    dst = os.path.join(tmp_path, name)
    shutil.copytree(src, dst)
    if make_bagit:
        bagit.make_bag(dst)
    return models.Package.objects.create(current_location=location, current_path=dst)


def test_transfer_indexing(
    transfer_backlog_location: models.Location, tmp_path: pathlib.Path
) -> None:
    package = _create_transfer_package(
        transfer_backlog_location, tmp_path, "tiny_transfer", "test1"
    )
    file_data = package._parse_mets(package.full_path)
    assert len(file_data["files"]) == 1
    assert file_data["dashboard_uuid"] == "f1d803b9-c429-441c-bc3a-d9d334ac71bc"
    assert file_data["creation_date"] == "2019-03-06T22:06:02"
    assert file_data["accession_id"] == "12345"
    assert file_data["transfer_uuid"] == "328f0967-94a0-4376-bf92-9224da033248"
    assert file_data["files"][0]["path"] == "test1/objects/foobar.bmp"
    package.index_file_data_from_transfer_mets()
    files = models.File.objects.filter(package=package)
    assert files.count() == 1
    assert files[0].name == "test1/objects/foobar.bmp"


def test_transfer_bagit_indexing(
    transfer_backlog_location: models.Location, tmp_path: pathlib.Path
) -> None:
    """Test that the path reflects the BagIt directory structure."""
    package = _create_transfer_package(
        transfer_backlog_location, tmp_path, "tiny_transfer", "test2", make_bagit=True
    )
    file_data = package._parse_mets(package.full_path)
    assert file_data["files"][0]["path"] == "test2/data/objects/foobar.bmp"
    package.index_file_data_from_transfer_mets()
    files = models.File.objects.filter(package=package)
    assert files[0].name == "test2/data/objects/foobar.bmp"
