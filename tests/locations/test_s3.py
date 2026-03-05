from pathlib import Path
from unittest import mock

import botocore
import pytest
from pytest_django.fixtures import SettingsWrapper

from archivematica.storage_service.locations import models


@pytest.fixture
@pytest.mark.django_db
def space(tmp_path):
    space_dir = tmp_path / "space"
    space_dir.mkdir()

    return models.Space.objects.create(
        access_protocol=models.Space.S3,
        path=space_dir,
        staging_path=space_dir,
    )


@pytest.fixture
@pytest.mark.django_db
def s3_space(space):
    return models.S3.objects.create(
        space=space,
        access_key_id="",
        secret_access_key="",
        endpoint_url="https://s3.amazonaws.com",
        region="us-east-1",
        bucket="test-bucket",
    )


@pytest.fixture
@pytest.mark.django_db
def aip_storage_location(s3_space):
    return models.Location.objects.create(
        description="S3",
        space=s3_space,
        relative_path="aips",
        purpose=models.Location.AIP_STORAGE,
    )


@pytest.fixture
@pytest.mark.django_db
def package(aip_storage_location):
    return models.Package.objects.create(
        current_location=aip_storage_location,
        current_path="small_compressed_bag.zip",
        package_type="AIP",
        status="Uploaded",
    )


@pytest.mark.django_db
def test_bucket_name(s3_space):
    assert s3_space.bucket_name == "test-bucket"


@pytest.mark.django_db
def test_bucket_name_falls_back_to_space_id(space, s3_space):
    s3_space.bucket = ""
    s3_space.save()

    assert s3_space.bucket_name == str(space.uuid)


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.return_value": {
                "LocationConstraint": "us-east-1",
                "ResponseMetadata": {},
            }
        }
    ),
)
def test_ensure_bucket_exists_logs_success_response(resource, s3_space, caplog):
    s3_space._ensure_bucket_exists()

    assert [r.message for r in caplog.records] == [
        f"Test the S3 bucket '{s3_space.bucket_name}' exists",
        "S3 bucket's response: {'LocationConstraint': 'us-east-1', 'ResponseMetadata': {}}",
    ]


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.side_effect": botocore.exceptions.ClientError(
                {"Error": {"Code": "Unknown", "Message": "my error message"}},
                "GetBucketLocation",
            )
        }
    ),
)
def test_ensure_bucket_exists_fails_if_unknown_error_is_returned(resource, s3_space):
    with pytest.raises(models.StorageException) as exc_info:
        s3_space._ensure_bucket_exists()

    # Extract the original ClientError
    client_error = exc_info.value.args[0]

    assert (
        client_error.args[0]
        == "An error occurred (Unknown) when calling the GetBucketLocation operation: my error message"
    )


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.side_effect": botocore.exceptions.BotoCoreError
        }
    ),
)
def test_ensure_bucket_exists_fails_if_botocore_error_is_returned(resource, s3_space):
    with pytest.raises(models.StorageException) as exc_info:
        s3_space._ensure_bucket_exists()

    log_prefix, error = exc_info.value.args

    assert log_prefix == "AWS error: %r"
    assert error.args[0] == "An unspecified error occurred"


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.side_effect": botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "bucket does not exist"}},
                "GetBucketLocation",
            ),
        }
    ),
)
def test_ensure_bucket_exists_creates_bucket_if_it_does_not_exist(
    resource, s3_space, caplog
):
    s3_space._ensure_bucket_exists()

    assert [r.message for r in caplog.records] == [
        f"Test the S3 bucket '{s3_space.bucket_name}' exists",
        f"Creating S3 bucket '{s3_space.bucket_name}'",
    ]


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.return_value": {
                "LocationConstraint": "planet-earth",
                "ResponseMetadata": {},
            }
        }
    ),
)
def test_ensure_bucket_exists_works_with_custom_endpoint_url(resource, s3_space):
    s3_space.access_key_id = "minio"
    s3_space.secret_access_key = "minio123"
    s3_space.region = "planet-earth"
    s3_space.endpoint_url = "https://localhost:9000"
    s3_space.save()

    s3_space._ensure_bucket_exists()

    resource.assert_called_once_with(
        service_name="s3",
        region_name="planet-earth",
        aws_access_key_id="minio",
        aws_secret_access_key="minio123",
        config=mock.ANY,
        endpoint_url="https://localhost:9000",
    )


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_bucket_location.side_effect": botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "bucket does not exist"}},
                "GetBucketLocation",
            ),
        }
    ),
)
def test_ensure_bucket_exists_works_with_any_region(resource, s3_space):
    s3_space.region = "ca-central-1"
    s3_space.save()

    s3_space._ensure_bucket_exists()

    resource.return_value.create_bucket.assert_called_once_with(
        Bucket=s3_space.bucket_name,
        CreateBucketConfiguration={"LocationConstraint": s3_space.region},
    )


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "meta.client.get_paginator.return_value": mock.Mock(
                **{
                    "paginate.side_effect": [
                        [{"Contents": [], "CommonPrefixes": [{"Prefix": "aips/"}]}],
                        [
                            {
                                "Contents": [],
                                "CommonPrefixes": [
                                    {"Prefix": "aips/myaips/"},
                                    {"Prefix": "aips/other/"},
                                ],
                            }
                        ],
                        [
                            {
                                "Contents": [
                                    {
                                        "Key": "aips/myaips/myaip.7z",
                                        "Size": 1024,
                                        "LastModified": "2024-01-01 00:00:00",
                                        "ETag": "2b5fbc705df14fd1c4fb022acfb4b3ca",
                                    }
                                ],
                                "CommonPrefixes": [{"Prefix": "aips/myaips/aips/"}],
                            }
                        ],
                        [
                            {
                                "Contents": [
                                    {
                                        "Key": "aips/other/other.7z",
                                        "Size": 512,
                                        "LastModified": "2023-01-01 00:00:00",
                                        "ETag": "9f11c93c2583100d80612e46db1c3bd5",
                                    }
                                ],
                                "CommonPrefixes": [{"Prefix": "aips/other/aips/"}],
                            }
                        ],
                    ]
                }
            )
        }
    ),
)
def test_browse(resource, s3_space, caplog):
    result = s3_space.browse("/")
    assert sorted(result.keys()) == ["directories", "entries", "properties"]
    assert sorted(result["directories"]) == ["aips"]
    assert sorted(result["entries"]) == ["aips"]

    result = s3_space.browse("/aips")

    assert sorted(result.keys()) == ["directories", "entries", "properties"]
    assert sorted(result["directories"]) == ["myaips", "other"]
    assert sorted(result["entries"]) == ["myaips", "other"]

    result = s3_space.browse("/aips/myaips")

    assert sorted(result.keys()) == ["directories", "entries", "properties"]
    assert sorted(result["directories"]) == ["aips"]
    assert sorted(result["entries"]) == ["aips", "myaip.7z"]
    assert result["properties"] == {
        "myaip.7z": {
            "size": 1024,
            "timestamp": "2024-01-01 00:00:00",
            "e_tag": "2b5fbc705df14fd1c4fb022acfb4b3ca",
        }
    }

    result = s3_space.browse("/aips/other")

    assert sorted(result.keys()) == ["directories", "entries", "properties"]
    assert sorted(result["directories"]) == ["aips"]
    assert sorted(result["entries"]) == ["aips", "other.7z"]
    assert result["properties"] == {
        "other.7z": {
            "size": 512,
            "timestamp": "2023-01-01 00:00:00",
            "e_tag": "9f11c93c2583100d80612e46db1c3bd5",
        }
    }

    assert [r.message for r in caplog.records] == [
        f"Browsing s3://{s3_space.bucket_name}// on S3 storage",
        f"Browsing s3://{s3_space.bucket_name}//aips on S3 storage",
        f"Browsing s3://{s3_space.bucket_name}//aips/myaips on S3 storage",
        f"Browsing s3://{s3_space.bucket_name}//aips/other on S3 storage",
    ]


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(**{"Bucket.return_value.objects.filter.return_value": []}),
)
def test_delete_path_fails_with_no_items(resource, s3_space, caplog):
    with pytest.raises(
        models.StorageException, match="No packages found in S3 at: aips/myaip.7z"
    ):
        s3_space.delete_path("/aips/myaip.7z")

    assert [r.message for r in caplog.records] == [
        "S3 path to delete /aips/myaip.7z begins with /; removing from path prior to deletion",
        "No packages found in S3 at: aips/myaip.7z",
    ]


@pytest.mark.django_db
@mock.patch(
    "boto3.resource",
    return_value=mock.Mock(
        **{
            "Bucket.return_value.objects.filter.return_value": [
                mock.Mock(
                    key="/aips/myaip.7z",
                    size=1024,
                    last_modified="2024-01-01 00:00:00",
                    e_tag="2b5fbc705df14fd1c4fb022acfb4b3ca",
                    **{"delete.return_value": {"success": True}},
                ),
            ]
        }
    ),
)
def test_delete_path_deletes_package(resource, s3_space, caplog):
    s3_space.delete_path("/aips/myaip.7z")

    assert [r.message for r in caplog.records] == [
        "S3 path to delete /aips/myaip.7z begins with /; removing from path prior to deletion",
        "S3 response when attempting to delete:",
        "{'success': True}",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("upload_use_threads", "download_use_threads"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_transfer_configs_use_settings_values(
    s3_space: models.S3,
    settings: SettingsWrapper,
    upload_use_threads: bool,
    download_use_threads: bool,
) -> None:
    settings.S3_UPLOAD_USE_THREADS = upload_use_threads
    settings.S3_DOWNLOAD_USE_THREADS = download_use_threads
    settings.S3_DOWNLOAD_ATTEMPTS = 7

    assert s3_space.upload_transfer_config.use_threads is upload_use_threads
    assert s3_space.download_transfer_config.use_threads is download_use_threads
    assert s3_space.download_transfer_config.num_download_attempts == 7


@pytest.mark.django_db
@pytest.mark.parametrize("use_threads", [True, False])
def test_upload_object_passes_upload_transfer_config_to_boto3(
    s3_space: models.S3,
    settings: SettingsWrapper,
    tmp_path: Path,
    use_threads: bool,
) -> None:
    settings.S3_UPLOAD_USE_THREADS = use_threads
    payload = tmp_path / "payload.txt"
    payload.write_text("hello")
    bucket = mock.Mock()

    s3_space.upload_object(bucket, "aips/payload.txt", str(payload))

    upload_fileobj = bucket.upload_fileobj
    upload_fileobj.assert_called_once()
    config = upload_fileobj.call_args.kwargs["Config"]

    assert config is s3_space.upload_transfer_config
    assert config.use_threads is use_threads


@pytest.mark.django_db
@pytest.mark.parametrize("use_threads", [True, False])
@mock.patch("boto3.resource")
def test_move_to_storage_service_passes_download_transfer_config_to_boto3(
    resource: mock.Mock,
    s3_space: models.S3,
    settings: SettingsWrapper,
    tmp_path: Path,
    use_threads: bool,
) -> None:
    resource.return_value = mock.Mock(
        **{
            "meta.client.get_bucket_location.return_value": {
                "LocationConstraint": "us-east-1",
                "ResponseMetadata": {},
            },
            "meta.client.head_object.return_value": {},
        }
    )

    settings.S3_DOWNLOAD_USE_THREADS = use_threads
    destination = tmp_path / "downloads" / "payload.7z"

    s3_space.move_to_storage_service("/aips/payload.txt", str(destination), None)

    download_file = resource.return_value.Bucket.return_value.download_file
    download_file.assert_called_once()
    config = download_file.call_args.kwargs["Config"]

    assert config is s3_space.download_transfer_config
    assert config.use_threads is use_threads


@pytest.mark.django_db
@mock.patch("boto3.resource")
def test_move_to_storage_service_uses_paginated_prefix_download_for_directories(
    resource: mock.Mock,
    s3_space: models.S3,
    tmp_path: Path,
) -> None:
    resource.return_value = mock.Mock(
        **{
            "meta.client.get_bucket_location.return_value": {
                "LocationConstraint": "us-east-1",
                "ResponseMetadata": {},
            },
            "meta.client.head_object.side_effect": botocore.exceptions.ClientError(
                {"Error": {"Code": "404", "Message": "not found"}},
                "HeadObject",
            ),
            "meta.client.get_paginator.return_value": mock.Mock(
                **{
                    "paginate.return_value": [
                        {"Contents": [{"Key": "aips/dir/file1.txt"}]},
                        {"Contents": [{"Key": "aips/dir/file2.txt"}]},
                    ]
                }
            ),
        }
    )

    destination = tmp_path / "downloads"
    s3_space.move_to_storage_service("/aips/dir", str(destination), None)

    resource.return_value.meta.client.get_paginator.assert_called_once_with(
        "list_objects_v2"
    )
    resource.return_value.meta.client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket=s3_space.bucket_name,
        Prefix="aips/dir/",
    )

    download_file = resource.return_value.Bucket.return_value.download_file
    assert download_file.call_count == 2
    downloaded_keys = [call.args[0] for call in download_file.call_args_list]
    assert downloaded_keys == ["aips/dir/file1.txt", "aips/dir/file2.txt"]


@pytest.mark.django_db
@mock.patch("time.sleep")
@mock.patch("boto3.resource")
def test_move_to_storage_service_retries_stalled_downloads(
    resource: mock.Mock,
    _sleep: mock.Mock,
    s3_space: models.S3,
    settings: SettingsWrapper,
    tmp_path: Path,
) -> None:
    resource.return_value = mock.Mock(
        **{
            "meta.client.get_bucket_location.return_value": {
                "LocationConstraint": "us-east-1",
                "ResponseMetadata": {},
            },
            "meta.client.head_object.return_value": {},
        }
    )
    resource.return_value.Bucket.return_value.download_file.side_effect = [
        botocore.exceptions.BotoCoreError(),
        None,
    ]
    settings.S3_TRANSFER_MAX_RETRIES = 2
    settings.S3_TRANSFER_RETRY_BACKOFF = 0
    destination = tmp_path / "downloads" / "payload.7z"

    s3_space.move_to_storage_service("/aips/payload.txt", str(destination), None)

    download_file = resource.return_value.Bucket.return_value.download_file
    assert download_file.call_count == 2


@pytest.mark.django_db
def test_upload_object_retries_stalled_uploads(
    s3_space: models.S3,
    settings: SettingsWrapper,
    tmp_path: Path,
) -> None:
    settings.S3_TRANSFER_MAX_RETRIES = 2
    settings.S3_TRANSFER_RETRY_BACKOFF = 0
    payload = tmp_path / "payload.txt"
    payload.write_text("hello")
    bucket = mock.Mock()
    bucket.upload_fileobj.side_effect = [botocore.exceptions.BotoCoreError(), None]

    with mock.patch("time.sleep") as _sleep:
        s3_space.upload_object(bucket, "aips/payload.txt", str(payload))

    assert bucket.upload_fileobj.call_count == 2
