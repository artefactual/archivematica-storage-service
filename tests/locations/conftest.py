"""Fixtures of the locations tests.

They create the rows of a Storage Service installation with the default
locations of the local filesystem space, the pipelines and packages that
the API and model tests share, and the Arkivum space.
"""

import datetime
import uuid

import pytest

from archivematica.storage_service.common import utils
from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.arkivum import Arkivum
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import PipelineFactory
from tests.factories import SpaceFactory

# The following fixtures create the default space and its locations.


@pytest.fixture
def default_space(make_space: SpaceFactory) -> models.Space:
    """The local filesystem space rooted at the root of the filesystem."""
    return make_space(path="/")


@pytest.fixture
def default_transfer_source(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.TRANSFER_SOURCE,
        relative_path="home",
    )


@pytest.fixture
def default_aip_storage(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.AIP_STORAGE,
        relative_path="var/archivematica/sharedDirectory/www/AIPsStore",
        description="Store AIP in standard Archivematica Directory",
    )


@pytest.fixture
def default_dip_storage(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.DIP_STORAGE,
        relative_path="var/archivematica/sharedDirectory/www/DIPsStore",
        description="Store DIP in standard Archivematica Directory",
    )


@pytest.fixture
def default_backlog(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.BACKLOG,
        relative_path="var/archivematica/sharedDirectory/www/AIPsStore/transferBacklog",
        description="Default transfer backlog",
    )


@pytest.fixture
def default_ss_internal(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.STORAGE_SERVICE_INTERNAL,
        relative_path="var/archivematica/storage_service",
        description="For storage service internal usage.",
    )


@pytest.fixture
def default_aip_recovery(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.AIP_RECOVERY,
        relative_path="var/archivematica/storage_service/recover",
        description="Default AIP recovery",
    )


@pytest.fixture
def default_currently_processing(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    return make_location(
        default_space,
        models.Location.CURRENTLY_PROCESSING,
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
def default_pipeline(make_pipeline: PipelineFactory) -> models.Pipeline:
    return make_pipeline(
        description="Test pipeline",
        remote_name="https://test-am-dashboard",
    )


# The following fixtures create the pipelines.


@pytest.fixture
def pipeline_rows(
    make_pipeline: PipelineFactory,
    default_transfer_source: models.Location,
    default_aip_storage: models.Location,
    default_dip_storage: models.Location,
    default_backlog: models.Location,
    default_aip_recovery: models.Location,
    default_currently_processing: models.Location,
) -> list[models.Pipeline]:
    """Three pipelines, two of them using the default locations."""
    alouette = make_pipeline(
        description="Archivematica on alouette",
        remote_name="127.0.0.1",
    )
    unnamed = make_pipeline(
        description="Test",
        remote_name="",
        api_username="",
        api_key="",
    )
    dashboard = make_pipeline(
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
def testing_aip_storage(
    make_location: LocationFactory, default_space: models.Space
) -> models.Location:
    """The AIP storage location at the root of the default space, which the
    tests point at their fixtures directory.
    """
    return make_location(
        default_space,
        models.Location.AIP_STORAGE,
        description="Testing directory AIP storage",
    )


def _create_package(
    make_package: PackageFactory,
    location: models.Location,
    current_path: str,
    **fields: object,
) -> models.Package:
    """Create a package uploaded before the statuses were written in capitals."""
    defaults: dict[str, object] = {"status": "Uploaded"}

    return make_package(location, current_path, **{**defaults, **fields})


@pytest.fixture
def images_transfer(
    make_package: PackageFactory, default_transfer_source: models.Location
) -> models.Package:
    """The transfer of the images, which has a file."""
    result = _create_package(
        make_package,
        default_transfer_source,
        "/dev/null/images-transfer-de1b31fa-97dd-48e0-8417-03be78359531",
        package_type="Transfer",
    )
    models.File.objects.create(
        package=result,
        name="test_sip/objects/file.txt",
        source_id=str(uuid.uuid4()),
        source_package=str(uuid.uuid4()),
        checksum="",
        origin=uuid.uuid4(),
    )

    return result


@pytest.fixture
def empty_transfer(
    make_package: PackageFactory, default_transfer_source: models.Location
) -> models.Package:
    package_uuid = uuid.uuid4()

    return _create_package(
        make_package,
        default_transfer_source,
        f"/dev/null/empty-transfer-{package_uuid}",
        uuid=package_uuid,
        package_type="Transfer",
        description="Package with no files",
    )


@pytest.fixture
def one_file_transfer(
    make_package: PackageFactory, default_transfer_source: models.Location
) -> models.Package:
    package_uuid = uuid.uuid4()
    result = _create_package(
        make_package,
        default_transfer_source,
        f"/dev/null/transfer-with-one-file-{package_uuid}",
        uuid=package_uuid,
        package_type="Transfer",
        description="Package with one file",
    )
    models.File.objects.create(
        package=result,
        name="test_sip/objects/file.txt",
        source_id=str(uuid.uuid4()),
        source_package=str(package_uuid),
        checksum="",
        origin=uuid.uuid4(),
    )

    return result


@pytest.fixture
def transfer_packages(
    images_transfer: models.Package,
    empty_transfer: models.Package,
    one_file_transfer: models.Package,
) -> list[models.Package]:
    """The three transfers in the transfer source."""
    return [images_transfer, empty_transfer, one_file_transfer]


@pytest.fixture
def working_bag(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    """The uncompressed bag of the fixtures directory."""
    return _create_package(
        make_package,
        testing_aip_storage,
        "working_bag",
        description="Small bagged package",
    )


@pytest.fixture
def broken_bag(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    """The uncompressed bag of the fixtures directory that misses a file."""
    return _create_package(
        make_package,
        testing_aip_storage,
        "broken_bag",
        description="Broken bag",
    )


@pytest.fixture
def zipped_bag(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    return _create_package(
        make_package,
        testing_aip_storage,
        "working_bag.zip",
        description="Small zipped bagged package",
    )


@pytest.fixture
def sevenzipped_bag(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    return _create_package(
        make_package,
        testing_aip_storage,
        "working_bag.7z",
        description="Small bagged 7zipped package",
        size=595,
    )


@pytest.fixture
def tar_gz_package(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    package_uuid = uuid.uuid4()

    return _create_package(
        make_package,
        testing_aip_storage,
        f"/dev/null/tar_gz_package-{package_uuid}.tar.gz",
        uuid=package_uuid,
        description="Small gzipped tar package",
    )


@pytest.fixture
def tricky_7z_package(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    """The 7z package whose name has the extensions of other archives."""
    package_uuid = uuid.uuid4()

    return _create_package(
        make_package,
        testing_aip_storage,
        f"/dev/null/a.bz2.tricky.7z.package-{package_uuid}.7z",
        uuid=package_uuid,
        description="Small 7z package with tricky filename",
    )


@pytest.fixture
def bag_packages(
    working_bag: models.Package,
    broken_bag: models.Package,
    zipped_bag: models.Package,
    sevenzipped_bag: models.Package,
    tar_gz_package: models.Package,
    tricky_7z_package: models.Package,
) -> list[models.Package]:
    """The bagged AIPs of the fixtures directory, compressed and not."""
    return [
        working_bag,
        broken_bag,
        zipped_bag,
        sevenzipped_bag,
        tar_gz_package,
        tricky_7z_package,
    ]


@pytest.fixture
def replicated_package(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    """A stored AIP with two stored replicas."""
    package_uuid = uuid.uuid4()
    path = utils.uuid_to_path(package_uuid)
    result = _create_package(
        make_package,
        testing_aip_storage,
        f"{path}/0f-{package_uuid}.7z",
        uuid=package_uuid,
        status=models.Package.UPLOADED,
        pointer_file_path=f"{path}/pointer.{package_uuid}.xml",
        size=299703,
    )
    for _ in range(2):
        replica_uuid = uuid.uuid4()
        path = utils.uuid_to_path(replica_uuid)
        _create_package(
            make_package,
            testing_aip_storage,
            f"{path}/0f-{replica_uuid}.7z",
            uuid=replica_uuid,
            status=models.Package.UPLOADED,
            pointer_file_path=f"{path}/pointer.{replica_uuid}.xml",
            size=299703,
            replicated_package=result,
        )

    return result


@pytest.fixture
def replicas(replicated_package: models.Package) -> list[models.Package]:
    """The two replicas of the replicated package."""
    return list(replicated_package.replicas.order_by("current_path"))


@pytest.fixture
def small_aic(
    make_package: PackageFactory, testing_aip_storage: models.Location
) -> models.Package:
    """The small AIC of the fixtures directory, whose UUID names its package
    and pointer file fixtures.
    """
    return _create_package(
        make_package,
        testing_aip_storage,
        "aicsmall_aic-4781e745-96bc-4b06-995c-ee59fddf856d.7z",
        uuid=uuid.UUID("4781e745-96bc-4b06-995c-ee59fddf856d"),
        status=models.Package.UPLOADED,
        package_type=models.Package.AIC,
        pointer_file_path="pointer.4781e745-96bc-4b06-995c-ee59fddf856d.xml",
        description="Small AIC",
        size=2195,
    )


@pytest.fixture
def replicated_packages(
    replicated_package: models.Package,
    replicas: list[models.Package],
    small_aic: models.Package,
) -> list[models.Package]:
    """A stored AIP and its two replicas, and a stored AIC."""
    return [replicated_package, *replicas, small_aic]


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
            event="post_store",
            uri="http://consumer.com/api/v1/file/<source_id>/",
            method="delete",
            body="",
            headers="",
        ),
        models.Callback.objects.create(
            event="post_store_aip",
            uri="http://consumer.com/api/v1/aip/<package_uuid>/",
            method="post",
            body='{"name": "<package_name>", "uuid": "<package_uuid>"}',
            headers="",
        ),
        models.Callback.objects.create(
            event="post_store_aic",
            uri="http://consumer.com/api/v1/aic/<package_uuid>/",
            method="post",
            body="",
            headers="",
        ),
        models.Callback.objects.create(
            event="post_store_aic",
            uri="http://consumer.com/api/v1/aic/<package_uuid>/",
            method="post",
            body="",
            headers="",
            enabled=False,
        ),
        models.Callback.objects.create(
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
def arkivum(make_space: SpaceFactory) -> Arkivum:
    space = make_space(
        access_protocol=models.Space.ARKIVUM,
        path="/mnt/arkivum",
        staging_path="/var/archivematica/storage_service/",
    )

    return Arkivum.objects.create(space=space, host="localhost:8443")


@pytest.fixture
def arkivum_aip_storage(
    make_location: LocationFactory, arkivum: Arkivum
) -> models.Location:
    return make_location(
        arkivum.space,
        models.Location.AIP_STORAGE,
        description="Arkivum AS",
    )


@pytest.fixture
def arkivum_pipeline(make_pipeline: PipelineFactory) -> models.Pipeline:
    return make_pipeline(
        description="Archivematica",
    )


@pytest.fixture
def arkivum_compressed_package(
    make_package: PackageFactory,
    arkivum_aip_storage: models.Location,
    arkivum_pipeline: models.Pipeline,
    default_ss_internal: models.Location,
) -> models.Package:
    """A compressed AIP being staged in the Arkivum space, with its pointer
    file in the internal location. Its UUID names the pointer file fixture.
    """
    package_uuid = uuid.UUID("c0f8498f-b92e-4a8b-8941-1b34ba062ed8")

    return _create_package(
        make_package,
        arkivum_aip_storage,
        "working_bag.zip",
        uuid=package_uuid,
        status=models.Package.STAGING,
        origin_pipeline=arkivum_pipeline,
        pointer_file_location=default_ss_internal,
        pointer_file_path=f"{utils.uuid_to_path(package_uuid)}/pointer.{package_uuid}.xml",
        size=2344125,
    )


@pytest.fixture
def arkivum_uncompressed_package(
    make_package: PackageFactory,
    arkivum_aip_storage: models.Location,
    arkivum_pipeline: models.Pipeline,
) -> models.Package:
    """An uncompressed AIP being staged in the Arkivum space."""
    return _create_package(
        make_package,
        arkivum_aip_storage,
        "working_bag/",
        status=models.Package.STAGING,
        origin_pipeline=arkivum_pipeline,
        pointer_file_path=None,
        size=2344125,
    )


@pytest.fixture
def arkivum_packages(
    arkivum_compressed_package: models.Package,
    arkivum_uncompressed_package: models.Package,
) -> list[models.Package]:
    """The packages being staged in the Arkivum space."""
    return [arkivum_compressed_package, arkivum_uncompressed_package]
