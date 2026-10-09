"""Fixtures of the locations tests.

They create the rows of a Storage Service installation with the default
locations of the local filesystem space, the pipelines and packages that
the API and model tests share, and the Arkivum space.
"""

import datetime
import uuid

import pytest
from django.contrib.auth.models import User
from tastypie.models import ApiKey

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.arkivum import Arkivum
from archivematica.storage_service.locations.models.local_filesystem import (
    LocalFilesystem,
)

# Users


@pytest.fixture
def api_user(django_user_model: type[User]) -> User:
    """The superuser of the API tests, whose password is "test"."""
    result = django_user_model.objects.create_user(
        username="test",
        password="test",
        email="test@test.com",
        is_superuser=True,
        is_staff=True,
    )
    ApiKey.objects.create(user=result, key="test")

    return result


@pytest.fixture
def nonadmin_user(django_user_model: type[User]) -> User:
    """A staff user without a role, whose password is "test"."""
    result = django_user_model.objects.create_user(
        username="nonadmin", password="test", email="test2@test.com", is_staff=True
    )
    ApiKey.objects.create(user=result, key="test")

    return result


# The following fixtures create the default space and its locations.


@pytest.fixture
def default_space(db: None) -> models.Space:
    """The local filesystem space rooted at the root of the filesystem."""
    result = models.Space.objects.create(
        uuid=uuid.UUID("7d20c992-bc92-4f92-a794-7161ff2cc08b"),
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path="/",
    )
    LocalFilesystem.objects.create(space=result)

    return result


@pytest.fixture
def default_transfer_source(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("4056b25d-6a85-4557-b9a5-9c85565fd892"),
        space=default_space,
        purpose=models.Location.TRANSFER_SOURCE,
        relative_path="home",
    )


@pytest.fixture
def default_aip_storage(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("99536e72-97af-4f0c-811e-06160a995c36"),
        space=default_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="var/archivematica/sharedDirectory/www/AIPsStore",
        description="Store AIP in standard Archivematica Directory",
    )


@pytest.fixture
def default_dip_storage(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("83805e08-44cf-408b-b805-49a312528e05"),
        space=default_space,
        purpose=models.Location.DIP_STORAGE,
        relative_path="var/archivematica/sharedDirectory/www/DIPsStore",
        description="Store DIP in standard Archivematica Directory",
    )


@pytest.fixture
def default_backlog(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("6e61aacf-8492-4382-8ef3-262cc5420259"),
        space=default_space,
        purpose=models.Location.BACKLOG,
        relative_path="var/archivematica/sharedDirectory/www/AIPsStore/transferBacklog",
        description="Default transfer backlog",
    )


@pytest.fixture
def default_ss_internal(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("72ee3a1a-9497-46db-aa58-56ea8d7fedc5"),
        space=default_space,
        purpose=models.Location.STORAGE_SERVICE_INTERNAL,
        relative_path="var/archivematica/storage_service",
        description="For storage service internal usage.",
    )


@pytest.fixture
def default_aip_recovery(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("932aeff2-f700-4098-bad0-91672363ec3f"),
        space=default_space,
        purpose=models.Location.AIP_RECOVERY,
        relative_path="var/archivematica/storage_service/recover",
        description="Default AIP recovery",
    )


@pytest.fixture
def default_currently_processing(default_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("213086c8-232e-4b9e-bb03-98fbc7a7966a"),
        space=default_space,
        purpose=models.Location.CURRENTLY_PROCESSING,
        relative_path="var/archivematica/sharedDirectory/",
    )


@pytest.fixture
def default_locations(
    default_transfer_source: models.Location,
    default_aip_storage: models.Location,
    default_dip_storage: models.Location,
    default_backlog: models.Location,
    default_ss_internal: models.Location,
    default_aip_recovery: models.Location,
    default_currently_processing: models.Location,
) -> list[models.Location]:
    """The locations of the default space, one per purpose."""
    return [
        default_transfer_source,
        default_aip_storage,
        default_dip_storage,
        default_backlog,
        default_ss_internal,
        default_aip_recovery,
        default_currently_processing,
    ]


@pytest.fixture
def default_pipeline(db: None) -> models.Pipeline:
    return models.Pipeline.objects.create(
        uuid=uuid.UUID("0cbf947a-1b19-4a01-a575-454078768fcd"),
        description="Test pipeline",
        remote_name="https://test-am-dashboard",
    )


@pytest.fixture
def base_rows(
    api_user: User,
    nonadmin_user: User,
    default_locations: list[models.Location],
    default_pipeline: models.Pipeline,
) -> None:
    """The users, the default space with its locations and the default
    pipeline.
    """


# The following fixtures create the pipelines.


@pytest.fixture
def pipeline_rows(
    default_transfer_source: models.Location,
    default_aip_storage: models.Location,
    default_dip_storage: models.Location,
    default_backlog: models.Location,
    default_aip_recovery: models.Location,
    default_currently_processing: models.Location,
) -> list[models.Pipeline]:
    """Three pipelines, two of them using the default locations."""
    alouette = models.Pipeline.objects.create(
        uuid=uuid.UUID("b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"),
        description="Archivematica on alouette",
        remote_name="127.0.0.1",
    )
    unnamed = models.Pipeline.objects.create(
        uuid=uuid.UUID("d2df89dc-9443-48dd-8983-55e9d1f92bcb"),
        description="Test",
        remote_name="",
        api_username="",
        api_key="",
    )
    dashboard = models.Pipeline.objects.create(
        uuid=uuid.UUID("1b6de7e3-0a72-4b23-8451-3ac858cc4ce4"),
        description="Test",
        remote_name="http://archivematica-dashboard:8000",
        api_username="test",
        api_key="test",
    )
    shared_locations = [
        default_transfer_source,
        default_aip_storage,
        default_currently_processing,
        default_backlog,
        default_dip_storage,
    ]
    alouette.location_set.add(*shared_locations, default_aip_recovery)
    unnamed.location_set.add(*shared_locations)

    return [alouette, unnamed, dashboard]


# The following fixtures create the packages of the tests.


@pytest.fixture
def testing_aip_storage(default_space: models.Space) -> models.Location:
    """The AIP storage location at the root of the default space, which the
    tests point at their fixtures directory.
    """
    return models.Location.objects.create(
        uuid=uuid.UUID("615103f0-0ee0-4a12-ba17-43192d1143ea"),
        space=default_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="",
        description="Testing directory AIP storage",
    )


def _create_package(
    location: models.Location, package_uuid: str, **fields: object
) -> models.Package:
    defaults: dict[str, object] = {"status": "Uploaded", "package_type": "AIP"}

    return models.Package.objects.create(
        uuid=uuid.UUID(package_uuid),
        current_location=location,
        **{**defaults, **fields},
    )


@pytest.fixture
def transfer_packages(
    default_transfer_source: models.Location,
) -> list[models.Package]:
    """Three transfers in the transfer source, two of them with a file."""
    images = _create_package(
        default_transfer_source,
        "e0a41934-c1d7-45ba-9a95-a7531c063ed1",
        package_type="Transfer",
        current_path="/dev/null/images-transfer-de1b31fa-97dd-48e0-8417-03be78359531",
    )
    empty = _create_package(
        default_transfer_source,
        "79245866-ca80-4f84-b904-a02b3e0ab621",
        package_type="Transfer",
        current_path="/dev/null/empty-transfer-79245866-ca80-4f84-b904-a02b3e0ab621",
        description="Package with no files",
    )
    one_file = _create_package(
        default_transfer_source,
        "a59033c2-7fa7-41e2-9209-136f07174692",
        package_type="Transfer",
        current_path="/dev/null/transfer-with-one-file-a59033c2-7fa7-41e2-9209-136f07174692",
        description="Package with one file",
    )
    models.File.objects.create(
        uuid=uuid.UUID("86bfde11-e2a1-4ee7-b98d-9556b5f05198"),
        package=images,
        name="test_sip/objects/file.txt",
        source_id="86bfde11-e2a1-4ee7-b98d-9556b5f05198",
        source_package="4b6c796b-0757-4d5f-8e79-51dede362520",
        checksum="",
        origin=uuid.UUID("bd17e3cf-afb6-4067-b7d0-472482767ee2"),
    )
    models.File.objects.create(
        uuid=uuid.UUID("bcd59769-0c6b-48cd-b54a-63092b9718fc"),
        package=one_file,
        name="test_sip/objects/file.txt",
        source_id="2b24a977-ad7a-4886-b17c-8b32ab4a7955",
        source_package="a59033c2-7fa7-41e2-9209-136f07174692",
        checksum="",
        origin=uuid.UUID("91d13621-d2c1-4c70-a67e-77e96dced036"),
    )

    return [images, empty, one_file]


@pytest.fixture
def bag_packages(testing_aip_storage: models.Location) -> list[models.Package]:
    """The bagged AIPs of the fixtures directory, compressed and not."""
    return [
        _create_package(
            testing_aip_storage,
            "0d4e739b-bf60-4b87-bc20-67a379b28cea",
            current_path="working_bag",
            description="Small bagged package",
        ),
        _create_package(
            testing_aip_storage,
            "9f260047-a9b7-4a75-bb6a-e8d94c83edd2",
            current_path="broken_bag",
            description="Broken bag",
        ),
        _create_package(
            testing_aip_storage,
            "6aebdb24-1b6b-41ab-b4a3-df9a73726a34",
            current_path="working_bag.zip",
            description="Small zipped bagged package",
        ),
        _create_package(
            testing_aip_storage,
            "88deec53-c7dc-4828-865c-7356386e9399",
            current_path="working_bag.7z",
            description="Small bagged 7zipped package",
            size=595,
        ),
        _create_package(
            testing_aip_storage,
            "473a9398-0024-4804-81da-38946040c8af",
            current_path="/dev/null/tar_gz_package-473a9398-0024-4804-81da-38946040c8af.tar.gz",
            description="Small gzipped tar package",
        ),
        _create_package(
            testing_aip_storage,
            "708f7a1d-dda4-46c7-9b3e-99e188eeb04c",
            current_path="/dev/null/a.bz2.tricky.7z.package-473a9398-0024-4804-81da-38946040c8af.7z",
            description="Small 7z package with tricky filename",
        ),
    ]


@pytest.fixture
def replicated_packages(
    testing_aip_storage: models.Location,
) -> list[models.Package]:
    """A stored AIP and its two replicas, and a stored AIC."""
    original = _create_package(
        testing_aip_storage,
        "f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04",
        status=models.Package.UPLOADED,
        current_path="f0df/dc4c/7ba1/4e3f/a972/f2c5/5d87/0d04/0f-f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04.7z",
        pointer_file_path="f0df/dc4c/7ba1/4e3f/a972/f2c5/5d87/0d04/pointer.f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04.xml",
        size=299703,
    )
    replicas = [
        _create_package(
            testing_aip_storage,
            package_uuid,
            status=models.Package.UPLOADED,
            current_path=f"{path}/0f-{package_uuid}.7z",
            pointer_file_path=f"{path}/pointer.{package_uuid}.xml",
            size=299703,
            replicated_package=original,
        )
        for package_uuid, path in [
            (
                "577f74bd-a283-49e0-b4e2-f8abb81d2566",
                "577f/74bd/a283/49e0/b4e2/f8ab/b81d/2566",
            ),
            (
                "2f62b030-c3f4-4ac1-950f-fe47d0ddcd14",
                "2f62/b030/c3f4/4ac1/950f/fe47/d0dd/cd14",
            ),
        ]
    ]
    aic = _create_package(
        testing_aip_storage,
        "4781e745-96bc-4b06-995c-ee59fddf856d",
        status=models.Package.UPLOADED,
        package_type=models.Package.AIC,
        current_path="aicsmall_aic-4781e745-96bc-4b06-995c-ee59fddf856d.7z",
        pointer_file_path="pointer.4781e745-96bc-4b06-995c-ee59fddf856d.xml",
        description="Small AIC",
        size=2195,
    )

    return [original, *replicas, aic]


@pytest.fixture
def package_rows(
    transfer_packages: list[models.Package],
    bag_packages: list[models.Package],
    replicated_packages: list[models.Package],
) -> list[models.Package]:
    """The thirteen packages of the package tests."""
    return [*transfer_packages, *bag_packages, *replicated_packages]


# The following fixtures create the callbacks and the fixity logs.


@pytest.fixture
def callback_rows(db: None) -> list[models.Callback]:
    """The callbacks of every event, one of them disabled."""
    return [
        models.Callback.objects.create(
            uuid=uuid.UUID("6020d3d9-ecb0-4339-8bbb-0d9ec1d6877b"),
            event="post_store",
            uri="http://consumer.com/api/v1/file/<source_id>/",
            method="delete",
            body="",
            headers="",
        ),
        models.Callback.objects.create(
            uuid=uuid.UUID("24eb7980-27de-4729-927a-ac91f726469d"),
            event="post_store_aip",
            uri="http://consumer.com/api/v1/aip/<package_uuid>/",
            method="post",
            body='{"name": "<package_name>", "uuid": "<package_uuid>"}',
            headers="",
        ),
        models.Callback.objects.create(
            uuid=uuid.UUID("6be67a5a-b970-4d88-b7dc-548195476853"),
            event="post_store_aic",
            uri="http://consumer.com/api/v1/aic/<package_uuid>/",
            method="post",
            body="",
            headers="",
        ),
        models.Callback.objects.create(
            uuid=uuid.UUID("6be67a5a-b970-4d88-b7dc-548195476853"),
            event="post_store_aic",
            uri="http://consumer.com/api/v1/aic/<package_uuid>/",
            method="post",
            body="",
            headers="",
            enabled=False,
        ),
        models.Callback.objects.create(
            uuid=uuid.UUID("ef0672a2-d0ed-474b-95f6-ff8f9ea1fc15"),
            event="post_store_dip",
            uri="https://consumer.com/api/v1/dip/<package_uuid>/stored",
            method="post",
            body='{"download_url": "http://ss.com/api/v2/file/<package_uuid>/download/"}',
            headers='{"Authorization": "Token token_string", "Origin": "http://ss.com"}',
            expected_status=202,
        ),
    ]


@pytest.fixture
def fixity_log_rows(transfer_packages: list[models.Package]) -> list[models.FixityLog]:
    """The fixity checks of the transfers, reported one year apart."""
    images, empty, _ = transfer_packages
    result = []
    for package, success, error_details, year in [
        (images, False, "Checksum failed.", 2015),
        (images, True, "", 2016),
        (images, False, "Other thing failed.", 2017),
        (empty, True, "", 2018),
    ]:
        log = models.FixityLog.objects.create(
            package=package, success=success, error_details=error_details
        )
        # The reporting time is set on every save, so it is written directly.
        models.FixityLog.objects.filter(pk=log.pk).update(
            datetime_reported=datetime.datetime(
                year, 12, 15, 3, 0, 5, 20871, tzinfo=datetime.timezone.utc
            )
        )
        log.refresh_from_db()
        result.append(log)

    return result


# The following fixtures create the Arkivum space and its packages.


@pytest.fixture
def arkivum(db: None) -> Arkivum:
    space = models.Space.objects.create(
        uuid=uuid.UUID("6fb34c82-4222-425e-b0ea-30acfd31f52e"),
        access_protocol=models.Space.ARKIVUM,
        path="/mnt/arkivum",
        staging_path="/var/archivematica/storage_service/",
    )

    return Arkivum.objects.create(space=space, host="localhost:8443")


@pytest.fixture
def arkivum_aip_storage(arkivum: Arkivum) -> models.Location:
    return models.Location.objects.create(
        uuid=uuid.UUID("d9d7db26-f7a1-40aa-9db1-806b4d3a61cd"),
        space=arkivum.space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="",
        description="Arkivum AS",
    )


@pytest.fixture
def arkivum_pipeline(db: None) -> models.Pipeline:
    return models.Pipeline.objects.create(
        uuid=uuid.UUID("7691b4bc-b76a-411c-b6a2-d16964018220"),
        description="Archivematica",
    )


@pytest.fixture
def arkivum_packages(
    arkivum_aip_storage: models.Location,
    arkivum_pipeline: models.Pipeline,
    default_ss_internal: models.Location,
) -> list[models.Package]:
    """A compressed and an uncompressed AIP being staged in the Arkivum
    space; the compressed one has a pointer file in the internal location.
    """
    package_uuid = "c0f8498f-b92e-4a8b-8941-1b34ba062ed8"
    compressed = _create_package(
        arkivum_aip_storage,
        package_uuid,
        status=models.Package.STAGING,
        origin_pipeline=arkivum_pipeline,
        current_path="working_bag.zip",
        pointer_file_location=default_ss_internal,
        pointer_file_path=f"c0f8/498f/b92e/4a8b/8941/1b34/ba06/2ed8/pointer.{package_uuid}.xml",
        size=2344125,
    )
    uncompressed = _create_package(
        arkivum_aip_storage,
        "e52c518d-fcf4-46cc-8581-bbc01aff7af3",
        status=models.Package.STAGING,
        origin_pipeline=arkivum_pipeline,
        current_path="working_bag/",
        pointer_file_path=None,
        size=2344125,
    )

    return [compressed, uncompressed]
