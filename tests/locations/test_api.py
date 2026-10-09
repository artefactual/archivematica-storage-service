import base64
import json
import os
import pathlib
import shutil
import uuid
from collections.abc import Iterator
from unittest import mock
from urllib.parse import urlparse

import pytest
from django.contrib.auth.models import User
from django.http import HttpResponseBase
from django.http import HttpResponseRedirect
from django.http import StreamingHttpResponse
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.administration import roles
from archivematica.storage_service.locations import models
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations.api.sword.views import (
    _parse_name_and_content_urls_from_mets_file,
)
from archivematica.storage_service.locations.models.arkivum import Arkivum
from archivematica.storage_service.locations.models.s3 import S3
from tests.factories import EventFactory
from tests.factories import LocationFactory
from tests.factories import SpaceFactory

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

# Arkivum assigned this identifier to the compressed package being staged.
ARKIVUM_IDENTIFIER = str(uuid.uuid4())


def _decode_response_content(response: HttpResponseBase) -> str:
    """Join the streamed content of a file response into a string."""
    assert isinstance(response, StreamingHttpResponse)
    chunks = response.streaming_content
    assert isinstance(chunks, Iterator)

    return b"".join(chunks).decode("utf8")


def _package_files(package: models.Package) -> list[dict[str, str]]:
    """Two files of the transfer, as the pipeline reports them to the API."""
    package_name = os.path.basename(package.current_path)
    origin = str(uuid.uuid4())

    return [
        {
            "relative_path": f"{package_name}/{name}",
            "fileuuid": str(uuid.uuid4()),
            "accessionid": "",
            "sipuuid": str(package.uuid),
            "origin": origin,
        }
        for name in ["1.txt", "2.txt"]
    ]


@pytest.fixture
def aip_storage_location(
    make_space: SpaceFactory, make_location: LocationFactory
) -> models.Location:
    """The AIP storage location of an S3 space, which replaces the shared one
    for the whole module: the shared package fixtures store their packages in
    the S3 space.
    """
    space = make_space(access_protocol=models.Space.S3)
    S3.objects.create(space=space)

    return make_location(space, models.Location.AIP_STORAGE, relative_path="aips")


@pytest.fixture
def package_storage(
    tmp_path: pathlib.Path,
    testing_aip_storage: models.Location,
    transfer_packages: list[models.Package],
    bag_packages: list[models.Package],
    arkivum: Arkivum,
    arkivum_packages: list[models.Package],
    arkivum_pipeline: models.Pipeline,
    default_ss_internal: models.Location,
) -> None:
    """The packages of the fixtures reachable on disk: the AIP storage location
    points at the fixtures directory, the Arkivum space and the internal
    location at the temporary directory, and every package has a pipeline.
    """
    ss_internal = tmp_path / "ss-internal"
    ss_internal.mkdir()
    shutil.copy(FIXTURES_DIR / "working_bag.zip", tmp_path)
    testing_aip_storage.relative_path = str(FIXTURES_DIR.relative_to(os.sep))
    testing_aip_storage.save()
    arkivum.space.path = str(tmp_path)
    arkivum.space.save()
    default_ss_internal.relative_path = str(ss_internal.relative_to(os.sep))
    default_ss_internal.save()
    # The compressed Arkivum package has been requested from Arkivum.
    compressed_package, _ = arkivum_packages
    compressed_package.misc_attributes = {"arkivum_identifier": ARKIVUM_IDENTIFIER}
    compressed_package.save()
    # Packages without a pipeline cannot be read through the API.
    models.Package.objects.all().update(origin_pipeline=arkivum_pipeline)


# The following tests cover the space API.


def test_space_requires_auth(client: Client) -> None:
    response = client.get(f"/api/v2/space/{uuid.uuid4()}/")
    assert response.status_code == 401


def test_space_non_admins_can_read_list(
    nonadmin_api_client: Client, default_space: models.Space
) -> None:
    response = nonadmin_api_client.get("/api/v2/space/")
    assert response.status_code == 200
    response_content = json.loads(response.text)
    assert len(response_content["objects"]) != 0


def test_space_non_admins_can_read_detail(
    nonadmin_api_client: Client, default_space: models.Space
) -> None:
    response = nonadmin_api_client.get(f"/api/v2/space/{default_space.uuid}/")
    assert response.status_code == 200
    assert response.text


def test_create_space(api_client: Client) -> None:
    data = {
        "access_protocol": "S3",
        "path": "",
        "staging_path": "/",
        # Specific to the S3 protocol.
        "endpoint_url": "http://127.0.0.1:12345",
        "access_key_id": "Cah4cae1",
        "secret_access_key": "Thu6Ahqu",
        "region": "us-west-2",
        "bucket": "test-bucket",
    }
    response = api_client.post(
        "/api/v2/space/", data=json.dumps(data), content_type="application/json"
    )
    response_data = json.loads(response.text)
    assert response.status_code == 201

    protocol_model = S3.objects.get(space_id=response_data["uuid"])
    assert protocol_model.endpoint_url == data["endpoint_url"]


def test_space_browse_doesnt_traverse_up(
    api_client: Client, make_space: SpaceFactory
) -> None:
    space = make_space(path="/home/foo")
    response = api_client.get(
        reverse(
            "browse",
            kwargs={"api_name": "v2", "resource_name": "space", "uuid": space.uuid},
        ),
        {"path": "/home/foo/../../etc"},
    )
    assert response.status_code == 400
    assert "The path parameter must be relative to the space path" in response.text


def test_space_browse_follow_symlinks(
    api_client: Client, make_space: SpaceFactory, tmp_path: pathlib.Path
) -> None:
    # Create a directory with two subdirectories and a file
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "child_1").mkdir()
    (out_dir / "child_1" / "file.txt").write_text("hello world")
    (out_dir / "child_2").mkdir()

    # Create a symlink for the space targetting the "out" directory
    space_dir = tmp_path / "space"
    space_dir.symlink_to(out_dir)

    space = make_space(path=str(space_dir))

    # Browse the space root directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={"api_name": "v2", "resource_name": "space", "uuid": space.uuid},
        ),
        {"path": str(space_dir)},
    )
    assert response.status_code == 200

    # Assert we get the two top level child directories
    response_content = json.loads(response.text)
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["directories"]
    ) == ["child_1", "child_2"]
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["entries"]
    ) == ["child_1", "child_2"]
    assert response_content["properties"] == {
        "child_1": {"object count": 1},
        "child_2": {"object count": 0},
    }

    # Browse the child_1 directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={"api_name": "v2", "resource_name": "space", "uuid": space.uuid},
        ),
        {"path": str(space_dir / "child_1")},
    )
    assert response.status_code == 200

    # Assert we get the inner text file
    response_content = json.loads(response.text)
    assert response_content["directories"] == []
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["entries"]
    ) == ["file.txt"]
    assert response_content["properties"] == {
        "file.txt": {"size": 11},
    }


def test_space_browse_with_symlinks_loop(
    api_client: Client, make_space: SpaceFactory, tmp_path: pathlib.Path
) -> None:
    # Create a symlink pointing to itself for the space path
    space_dir = tmp_path / "space"
    space_dir.symlink_to(space_dir)

    space = make_space(path=str(space_dir))

    # Browse the space root directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={"api_name": "v2", "resource_name": "space", "uuid": space.uuid},
        ),
        {"path": str(space_dir)},
    )
    assert response.status_code == 400


# The following tests cover the location API.


def test_location_requires_auth(client: Client) -> None:
    response = client.post(f"/api/v2/location/{uuid.uuid4()}/")
    assert response.status_code == 401


def test_location_non_admins_can_read_list(
    nonadmin_api_client: Client, default_locations: list[models.Location]
) -> None:
    response = nonadmin_api_client.get("/api/v2/location/")
    assert response.status_code == 200
    response_content = json.loads(response.text)
    assert len(response_content["objects"]) != 0


def test_location_non_admins_can_read_detail(
    nonadmin_api_client: Client, default_currently_processing: models.Location
) -> None:
    response = nonadmin_api_client.get(
        f"/api/v2/location/{default_currently_processing.uuid}/"
    )
    assert response.status_code == 200
    assert response.text


def test_non_admins_cannot_create_location(
    api_client: Client,
    api_user: User,
    default_space: models.Space,
    pipeline_rows: list[models.Pipeline],
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    alouette, *_ = pipeline_rows
    data = {
        "space": f"/api/v2/space/{default_space.uuid}/",
        "description": "automated workflow",
        "relative_path": "automated-workflow/foo/bar",
        "purpose": "TS",
        "pipeline": [f"/api/v2/pipeline/{alouette.uuid}/"],
    }

    response = api_client.post(
        "/api/v2/location/", data=json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 401


def test_create_location(
    api_client: Client,
    default_space: models.Space,
    pipeline_rows: list[models.Pipeline],
) -> None:
    alouette, *_ = pipeline_rows
    data = {
        "space": f"/api/v2/space/{default_space.uuid}/",
        "description": "automated workflow",
        "relative_path": "automated-workflow/foo/bar",
        "purpose": "TS",
        "pipeline": [f"/api/v2/pipeline/{alouette.uuid}/"],
    }

    response = api_client.post(
        "/api/v2/location/", data=json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 201

    # Verify content
    body = json.loads(response.text)
    assert body["description"] == data["description"]
    assert body["purpose"] == data["purpose"]
    assert body["path"] == "{}{}".format(default_space.path, data["relative_path"])
    assert body["enabled"] is True
    assert data["pipeline"][0] in body["pipeline"]

    # Verify that the record was populated properly
    location = models.Location.objects.get(uuid=body["uuid"])
    assert location.purpose == data["purpose"]
    assert location.relative_path == data["relative_path"]
    assert location.description == data["description"]


def test_create_default_location(
    api_client: Client,
    default_space: models.Space,
    pipeline_rows: list[models.Pipeline],
) -> None:
    """Test that a new created location can be marked as default.

    Storage Service allows users to define a location the default one for
    its purpose application-wise.

    In our fixtures we already have a TS added. We're going to add a new
    one and confirm that it can be marked as the new default.
    """
    alouette, *_ = pipeline_rows
    new_default_ts_location = {
        "space": f"/api/v2/space/{default_space.uuid}/",
        "description": "new location",
        "relative_path": "new-location/foo/bar",
        "purpose": "TS",
        "pipeline": [f"/api/v2/pipeline/{alouette.uuid}/"],
        "default": True,
    }

    def _get_default_ts() -> HttpResponseBase:
        return api_client.get(
            "/api/v2/location/default/TS/", content_type="application/json"
        )

    response = _get_default_ts()
    assert response.status_code == 404

    # Create default location.
    response = api_client.post(
        "/api/v2/location/",
        data=json.dumps(new_default_ts_location),
        content_type="application/json",
    )
    body = json.loads(response.text)

    response = _get_default_ts()
    assert isinstance(response, HttpResponseRedirect)
    assert response.status_code == 302
    assert response.url == "/api/v2/location/{}/".format(body["uuid"])


@pytest.fixture
def move_files_data(
    default_backlog: models.Location, pipeline_rows: list[models.Pipeline]
) -> dict[str, object]:
    """A request to move files from the backlog on behalf of a pipeline."""
    alouette, *_ = pipeline_rows

    return {
        "origin_location": f"/api/v2/location/{default_backlog.uuid}/",
        "files": [{"source": "foo", "destination": "bar"}],
        "pipeline": f"/api/v2/pipeline/{alouette.uuid}/",
    }


def test_cant_move_from_non_existant_locations(
    api_client: Client,
    default_currently_processing: models.Location,
    move_files_data: dict[str, object],
) -> None:
    move_files_data["origin_location"] = f"/api/v2/location/{uuid.uuid4()}/"
    response = api_client.post(
        f"/api/v2/location/{default_currently_processing.uuid}/",
        data=json.dumps(move_files_data),
        content_type="application/json",
    )
    # Verify error
    assert response.status_code == 404
    assert "not a link to a valid Location" in response.text


def test_cant_move_to_non_existant_locations(
    api_client: Client, move_files_data: dict[str, object]
) -> None:
    response = api_client.post(
        f"/api/v2/location/{uuid.uuid4()}/",
        data=json.dumps(move_files_data),
        content_type="application/json",
    )
    # Verify error
    assert response.status_code == 404


def test_cant_move_from_disabled_locations(
    api_client: Client,
    default_backlog: models.Location,
    default_currently_processing: models.Location,
    move_files_data: dict[str, object],
) -> None:
    # Set origin location disabled
    default_backlog.enabled = False
    default_backlog.save()
    # Send request
    response = api_client.post(
        f"/api/v2/location/{default_currently_processing.uuid}/",
        data=json.dumps(move_files_data),
        content_type="application/json",
    )
    # Verify error
    assert response.status_code == 404
    assert "not a link to a valid Location" in response.text


def test_cant_move_to_disabled_locations(
    api_client: Client,
    default_currently_processing: models.Location,
    move_files_data: dict[str, object],
) -> None:
    # Set posting to location disabled
    default_currently_processing.enabled = False
    default_currently_processing.save()
    # Send request
    response = api_client.post(
        f"/api/v2/location/{default_currently_processing.uuid}/",
        data=json.dumps(move_files_data),
        content_type="application/json",
    )
    # Verify error
    assert response.status_code == 404


def test_location_browse_doesnt_traverse_up(
    api_client: Client, make_space: SpaceFactory, make_location: LocationFactory
) -> None:
    location = make_location(
        make_space(path="/home"), models.Location.TRANSFER_SOURCE, relative_path="foo"
    )
    response = api_client.get(
        reverse(
            "browse",
            kwargs={
                "api_name": "v2",
                "resource_name": "location",
                "uuid": location.uuid,
            },
        ),
        {"path": base64.b64encode(b"/home")},
    )
    assert response.status_code == 400
    assert "The path parameter must be relative to the location path" in response.text


def test_location_browse_follow_symlinks(
    api_client: Client,
    make_space: SpaceFactory,
    make_location: LocationFactory,
    tmp_path: pathlib.Path,
) -> None:
    # Create a directory with two subdirectories and a file
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "child_1").mkdir()
    (out_dir / "child_1" / "file.txt").write_text("hello world")
    (out_dir / "child_2").mkdir()

    # Create a directory for the space
    space_dir = tmp_path / "space"
    space_dir.mkdir()

    # Create a symlink for the location targetting the "out" directory
    location_dir = space_dir / "location"
    location_dir.symlink_to(out_dir)

    location = make_location(
        make_space(path=str(space_dir)),
        models.Location.TRANSFER_SOURCE,
        relative_path="location",
    )

    # Browse the location root directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={
                "api_name": "v2",
                "resource_name": "location",
                "uuid": location.uuid,
            },
        ),
        {"path": base64.b64encode(str(location_dir).encode())},
    )
    assert response.status_code == 200

    # Assert we get the two top level child directories
    response_content = json.loads(response.text)
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["directories"]
    ) == ["child_1", "child_2"]
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["entries"]
    ) == ["child_1", "child_2"]
    assert response_content["properties"] == {
        base64.b64encode(b"child_1").decode(): {"object count": 1},
        base64.b64encode(b"child_2").decode(): {"object count": 0},
    }

    # Browse the child_1 directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={
                "api_name": "v2",
                "resource_name": "location",
                "uuid": location.uuid,
            },
        ),
        {"path": base64.b64encode(str(location_dir / "child_1").encode())},
    )
    assert response.status_code == 200

    # Assert we get the inner text file
    response_content = json.loads(response.text)
    assert response_content["directories"] == []
    assert sorted(
        base64.b64decode(e).decode() for e in response_content["entries"]
    ) == ["file.txt"]
    assert response_content["properties"] == {
        base64.b64encode(b"file.txt").decode(): {"size": 11},
    }


def test_location_browse_with_symlinks_loop(
    api_client: Client,
    make_space: SpaceFactory,
    make_location: LocationFactory,
    tmp_path: pathlib.Path,
) -> None:
    # Create a directory for the space
    space_dir = tmp_path / "space"
    space_dir.mkdir()

    # Create a symlink pointing to itself for the location path
    location_dir = space_dir / "location"
    location_dir.symlink_to(location_dir)

    location = make_location(
        make_space(path=str(space_dir)),
        models.Location.TRANSFER_SOURCE,
        relative_path="location",
    )

    # Browse the location root directory
    response = api_client.get(
        reverse(
            "browse",
            kwargs={
                "api_name": "v2",
                "resource_name": "location",
                "uuid": location.uuid,
            },
        ),
        {"path": base64.b64encode(str(location_dir).encode())},
    )
    assert response.status_code == 400


# The following tests cover the package API.


def test_package_requires_auth(client: Client) -> None:
    package_uuid = uuid.uuid4()
    urls = [
        "/api/v2/file/metadata/",
        f"/api/v2/file/{package_uuid}/contents/",
        f"/api/v2/file/{package_uuid}/download/",
        f"/api/v2/file/{package_uuid}/extract_file/",
    ]
    # Get metadata
    assert [client.get(url).status_code for url in urls] == [401] * len(urls)


def test_package_non_admins_can_read_list(
    api_client: Client, api_user: User, package_storage: None
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    response = api_client.get("/api/v2/file/")
    assert response.status_code == 200
    response_content = json.loads(response.text)
    assert len(response_content["objects"]) != 0


def test_package_non_admins_can_read_detail(
    api_client: Client,
    api_user: User,
    package_storage: None,
    working_bag: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    response = api_client.get(f"/api/v2/file/{working_bag.uuid}/")
    assert response.status_code == 200
    assert response.text


def test_non_admins_cant_reindex(
    api_client: Client,
    api_user: User,
    package_storage: None,
    working_bag: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    response = api_client.post(f"/api/v2/file/{working_bag.uuid}/reindex/")
    assert response.status_code == 401


def test_non_admins_cant_reingest(
    api_client: Client,
    api_user: User,
    package_storage: None,
    working_bag: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    data = {
        "pipeline": str(uuid.uuid4()),
        "reingest_type": "FULL",
    }
    response = api_client.post(
        f"/api/v2/file/{working_bag.uuid}/reingest/",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_non_admins_cant_move(
    api_client: Client,
    api_user: User,
    package_storage: None,
    working_bag: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    data = {
        "location_uuid": str(uuid.uuid4()),
    }
    response = api_client.post(
        f"/api/v2/file/{working_bag.uuid}/move/",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_non_admins_cant_add_file_to_package(
    api_client: Client,
    api_user: User,
    package_storage: None,
    empty_transfer: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    data = _package_files(empty_transfer)
    response = api_client.put(
        f"/api/v2/file/{empty_transfer.uuid}/contents/",
        data=json.dumps(data),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_non_admins_cant_delete_file_from_package(
    api_client: Client,
    api_user: User,
    package_storage: None,
    empty_transfer: models.Package,
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    response = api_client.delete(
        f"/api/v2/file/{empty_transfer.uuid}/contents/",
    )
    assert response.status_code == 401


def test_file_data_returns_metadata_given_relative_path(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    path = "test_sip/objects/file.txt"
    response = api_client.get("/api/v2/file/metadata/", {"relative_path": path})
    assert response.status_code == 200
    assert response["content-type"] == "application/json"
    body = json.loads(response.text)
    assert body[0]["relative_path"] == path
    assert body[0]["fileuuid"] == images_transfer.file_set.get().source_id


def test_file_data_returns_bad_response_with_no_accepted_parameters(
    api_client: Client,
) -> None:
    response = api_client.post("/api/v2/file/metadata/")
    assert response.status_code == 400


def test_file_data_returns_404_if_no_file_found(api_client: Client) -> None:
    response = api_client.get("/api/v2/file/metadata/", {"fileuuid": "nosuchfile"})
    assert response.status_code == 404


def test_package_contents_returns_metadata(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    response = api_client.get(f"/api/v2/file/{images_transfer.uuid}/contents/")
    assert response.status_code == 200
    assert response["content-type"] == "application/json"
    body = json.loads(response.text)
    assert body["success"] is True
    assert len(body["files"]) == 1
    assert body["files"][0]["name"] == "test_sip/objects/file.txt"


def test_adding_package_files_returns_400_with_empty_post_body(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    response = api_client.put(
        f"/api/v2/file/{images_transfer.uuid}/contents/",
        data="",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_adding_package_files_returns_400_if_post_body_is_not_json(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    response = api_client.put(
        f"/api/v2/file/{images_transfer.uuid}/contents/",
        data="not json!",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_adding_package_files_returns_400_if_post_body_is_not_a_list(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    response = api_client.put(
        f"/api/v2/file/{images_transfer.uuid}/contents/",
        data="{}",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_adding_package_files_returns_400_if_expected_fields_are_missing(
    api_client: Client, package_storage: None, images_transfer: models.Package
) -> None:
    body = [{"relative_path": "/dev/null"}]
    response = api_client.put(
        f"/api/v2/file/{images_transfer.uuid}/contents/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_adding_files_to_package_returns_200_for_empty_list(
    api_client: Client, package_storage: None, empty_transfer: models.Package
) -> None:
    response = api_client.put(
        f"/api/v2/file/{empty_transfer.uuid}/contents/",
        data="[]",
        content_type="application/json",
    )
    assert response.status_code == 200


def test_adding_files_to_package(
    api_client: Client, package_storage: None, empty_transfer: models.Package
) -> None:
    assert empty_transfer.file_set.count() == 0

    body = _package_files(empty_transfer)

    response = api_client.put(
        f"/api/v2/file/{empty_transfer.uuid}/contents/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert empty_transfer.file_set.count() == 2


def test_removing_file_from_package(
    api_client: Client, package_storage: None, one_file_transfer: models.Package
) -> None:
    assert one_file_transfer.file_set.count() == 1

    response = api_client.delete(f"/api/v2/file/{one_file_transfer.uuid}/contents/")
    assert response.status_code == 204
    assert one_file_transfer.file_set.count() == 0


def test_download_compressed_package(
    api_client: Client, package_storage: None, zipped_bag: models.Package
) -> None:
    """It should return the package."""
    response = api_client.get(f"/api/v2/file/{zipped_bag.uuid}/download/")
    assert response.status_code == 200
    assert response["content-type"] == "application/zip"
    assert response["content-disposition"] == 'attachment; filename="working_bag.zip"'


def test_download_uncompressed_package(
    api_client: Client, package_storage: None, working_bag: models.Package
) -> None:
    """It should tar a package before downloading."""
    response = api_client.get(f"/api/v2/file/{working_bag.uuid}/download/")
    assert response.status_code == 200
    assert response["content-type"] == "application/x-tar"
    assert response["content-disposition"] == 'attachment; filename="working_bag.tar"'
    content = _decode_response_content(response)
    assert "bag-info.txt" in content
    assert "bagit.txt" in content
    assert "manifest-md5.txt" in content
    assert "tagmanifest-md5.txt" in content
    assert "test.txt" in content


def test_download_lockss_chunk_incorrect(
    api_client: Client, package_storage: None, working_bag: models.Package
) -> None:
    """It should default to the local path if a chunk ID is provided but package isn't in LOCKSS."""
    response = api_client.get(
        f"/api/v2/file/{working_bag.uuid}/download/",
        data={"chunk_number": 1},
    )
    assert response.status_code == 200
    assert response["content-type"] == "application/x-tar"
    assert response["content-disposition"] == 'attachment; filename="working_bag.tar"'
    content = _decode_response_content(response)
    assert "bag-info.txt" in content
    assert "bagit.txt" in content
    assert "manifest-md5.txt" in content
    assert "tagmanifest-md5.txt" in content
    assert "test.txt" in content


def test_download_package_not_exist(api_client: Client) -> None:
    """It should return 404 for a non-existant package."""
    response = api_client.get(
        f"/api/v2/file/{uuid.uuid4()}/download/",
        data={"chunk_number": 1},
    )
    assert response.status_code == 404


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "id": ARKIVUM_IDENTIFIER,
                    "status": "Scheduled",
                    "originalSize": "775702",
                    "actualSize": "775702",
                    "originalChecksum": "5a44c7ba5bbe4ec867233d67e4806848",
                    "originalChecksumAlgorithm": "md5",
                    "originalCompressionAlgorithm": "",
                    "fileInformation": {"replicationState": "yellow"},
                },
            }
        )
    ],
)
def test_download_package_arkivum_not_available(
    requests_get: mock.MagicMock,
    api_client: Client,
    package_storage: None,
    arkivum_compressed_package: models.Package,
) -> None:
    """It should return 202 if the file is in Arkivum but only on tape."""
    response = api_client.get(
        f"/api/v2/file/{arkivum_compressed_package.uuid}/download/"
    )
    assert response.status_code == 202
    j = json.loads(response.text)
    assert j["error"] is False
    assert (
        j["message"]
        == "File is not locally available.  Contact your storage administrator to fetch it."
    )


@mock.patch(
    "requests.get",
    side_effect=[mock.Mock(**{"status_code": 404})],
)
def test_download_package_arkivum_error(
    requests_get: mock.MagicMock,
    api_client: Client,
    package_storage: None,
    arkivum_compressed_package: models.Package,
) -> None:
    """It should return 502 error from Arkivum."""
    response = api_client.get(
        f"/api/v2/file/{arkivum_compressed_package.uuid}/download/"
    )
    assert response.status_code == 502
    j = json.loads(response.text)
    assert j["error"] is True
    assert "Error" in j["message"] and "Arkivum" in j["message"]


def test_download_file_no_path(
    api_client: Client, package_storage: None, working_bag: models.Package
) -> None:
    """It should return 400 Bad Request"""
    response = api_client.get(f"/api/v2/file/{working_bag.uuid}/extract_file/")
    assert response.status_code == 400
    assert "relative_path_to_file" in response.text


def test_download_file_from_compressed(
    api_client: Client, package_storage: None, zipped_bag: models.Package
) -> None:
    """It should extract and return the file."""
    response = api_client.get(
        f"/api/v2/file/{zipped_bag.uuid}/extract_file/",
        data={"relative_path_to_file": "working_bag/data/test.txt"},
    )
    assert response.status_code == 200
    assert response["content-type"] == "text/plain"
    assert response["content-disposition"] == 'attachment; filename="test.txt"'
    content = _decode_response_content(response)
    assert content == "test"


def test_download_file_from_uncompressed(
    api_client: Client, package_storage: None, working_bag: models.Package
) -> None:
    """It should return the file."""
    response = api_client.get(
        f"/api/v2/file/{working_bag.uuid}/extract_file/",
        data={"relative_path_to_file": "working_bag/data/test.txt"},
    )
    assert response.status_code == 200
    assert response["content-type"] == "text/plain"
    assert response["content-disposition"] == 'attachment; filename="test.txt"'
    content = _decode_response_content(response)
    assert content == "test"


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "fileInformation": {"replicationState": "yellow"},
                },
            }
        )
    ],
)
def test_download_file_arkivum_not_available(
    requests_get: mock.MagicMock,
    api_client: Client,
    package_storage: None,
    arkivum_compressed_package: models.Package,
) -> None:
    """It should return 202 if the file is in Arkivum but only on tape."""
    response = api_client.get(
        f"/api/v2/file/{arkivum_compressed_package.uuid}/extract_file/",
        data={"relative_path_to_file": "working_bag/data/test.txt"},
    )
    assert response.status_code == 202
    j = json.loads(response.text)
    assert j["error"] is False
    assert (
        j["message"]
        == "File is not locally available.  Contact your storage administrator to fetch it."
    )


@mock.patch(
    "requests.get",
    side_effect=[mock.Mock(**{"status_code": 404})],
)
def test_download_file_arkivum_error(
    requests_get: mock.MagicMock,
    api_client: Client,
    package_storage: None,
    arkivum_compressed_package: models.Package,
) -> None:
    """It should return 502 error from Arkivum."""
    response = api_client.get(
        f"/api/v2/file/{arkivum_compressed_package.uuid}/extract_file/",
        data={"relative_path_to_file": "working_bag/data/test.txt"},
    )
    assert response.status_code == 502
    j = json.loads(response.text)
    assert j["error"] is True
    assert "Error" in j["message"] and "Arkivum" in j["message"]


@pytest.mark.parametrize(
    "view_name, expected_status",
    [
        ("delete_aip", models.Package.DEL_REQ),
        ("recover_aip", models.Package.RECOVER_REQ),
    ],
    ids=["delete_aip", "recover_aip"],
)
def test_request_view_updates_package_status(
    api_client: Client,
    api_user: User,
    package: models.Package,
    pipeline: models.Pipeline,
    view_name: str,
    expected_status: str,
) -> None:
    api_client.post(
        f"/api/v2/file/{package.uuid}/{view_name}/",
        data=json.dumps(
            {
                "event_reason": "Some justification",
                "pipeline": str(pipeline.uuid),
                "user_email": "test@example.com",
                "user_id": api_user.id,
            }
        ),
        content_type="application/json",
    )
    # Verify its status was updated
    assert models.Package.objects.get(uuid=package.uuid).status == expected_status


# The following tests cover the SWORD API.


def test_removes_forward_slash_parse_fedora_mets() -> None:
    """It should remove forward slashes in the deposit name and all
    filenames extracted from a Fedora METS file.
    """
    fedora_mets_path = os.path.join(FIXTURES_DIR, "fedora_mets_slash.xml")
    mets_parse = _parse_name_and_content_urls_from_mets_file(fedora_mets_path)
    fileobjs = mets_parse["objects"]
    assert "/" not in mets_parse["deposit_name"]
    assert len(fileobjs) > 0
    assert [fileobj for fileobj in fileobjs if "/" in fileobj["filename"]] == []


# The following tests cover the pipeline API.


def test_pipeline_non_admins_can_read_list(
    api_client: Client, api_user: User, default_pipeline: models.Pipeline
) -> None:
    api_user.set_role(roles.USER_ROLE_READER)
    response = api_client.get("/api/v2/pipeline/")
    assert response.status_code == 200
    response_content = json.loads(response.text)
    assert len(response_content["objects"]) != 0


def test_pipeline_non_admins_can_read_detail(
    nonadmin_api_client: Client, default_pipeline: models.Pipeline
) -> None:
    response = nonadmin_api_client.get(f"/api/v2/pipeline/{default_pipeline.uuid}/")
    assert response.status_code == 200
    assert response.text


def test_pipeline_create(api_client: Client) -> None:
    data = {
        "uuid": str(uuid.uuid4()),
        "description": "My pipeline",
        "remote_name": "https://archivematica-dashboard:8080",
        "api_key": "test",
        "api_username": "test",
    }
    response = api_client.post(
        "/api/v2/pipeline/", data=json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 201

    pipeline = models.Pipeline.objects.get(uuid=data["uuid"])
    assert pipeline.parse_and_fix_url(pipeline.remote_name) == urlparse(
        data["remote_name"]
    )

    # When undefined the remote_name field should be populated after the
    # REMOTE_ADDR header.
    data["uuid"] = str(uuid.uuid4())
    del data["remote_name"]
    response = api_client.post(
        "/api/v2/pipeline/",
        data=json.dumps(data),
        content_type="application/json",
        REMOTE_ADDR="192.168.0.10",
    )
    assert response.status_code == 201
    pipeline = models.Pipeline.objects.get(uuid=data["uuid"])
    assert pipeline.parse_and_fix_url(pipeline.remote_name) == urlparse(
        "http://192.168.0.10"
    )


def test_pipeline_create_without_api_key_stores_empty_string(
    api_client: Client,
) -> None:
    pipeline_uuid = str(uuid.uuid4())
    data = {
        "uuid": pipeline_uuid,
        "description": "My pipeline without api key",
        "remote_name": "https://archivematica-dashboard:8080",
        "api_username": "test",
    }

    response = api_client.post(
        "/api/v2/pipeline/", data=json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 201

    pipeline = models.Pipeline.objects.get(uuid=pipeline_uuid)
    assert pipeline.api_key == ""


@pytest.fixture
def compressed_bag_fixture_path() -> pathlib.Path:
    return FIXTURES_DIR / "working_bag.zip"


@pytest.fixture
def s3_resource(
    compressed_bag_fixture_path: pathlib.Path, aip_storage_location: models.Location
) -> mock.Mock:
    """Mock the S3 bucket interactions in S3.move_to_storage_service."""

    def download_file(_key: str, dest_file: str, Config: object | None = None) -> None:
        shutil.copy(compressed_bag_fixture_path, dest_file)

    return mock.Mock(
        **{
            "Bucket.side_effect": [
                mock.Mock(
                    **{
                        "download_file.side_effect": download_file,
                    }
                ),
                mock.Mock(
                    **{
                        "objects.filter.return_value": [
                            mock.Mock(
                                key=f"{aip_storage_location.relative_path}/{compressed_bag_fixture_path.name}"
                            )
                        ]
                    }
                ),
            ]
        }
    )


@mock.patch("boto3.resource")
def test_s3_space_deletes_temporary_files_after_extracting_file(
    resource: mock.MagicMock,
    admin_client: Client,
    s3_resource: mock.Mock,
    package: models.Package,
    ss_internal_location: models.Location,
) -> None:
    # Mock the S3 bucket interactions.
    resource.side_effect = [s3_resource]

    # Extract a file from the compressed AIP.
    response = admin_client.get(
        reverse(
            "extract_file_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"relative_path_to_file": "working_bag/data/test.txt"},
    )

    # Verify the response attributes.
    assert response.status_code == 200
    assert response["content-type"] == "text/plain"
    assert response["content-disposition"] == 'attachment; filename="test.txt"'

    # Verify the contents of the extracted file.
    result = b"".join(response.streaming_content)
    assert result.decode() == "test"

    # Verify there are no temporary files left in the internal processing location.
    assert list(pathlib.Path(ss_internal_location.full_path).iterdir()) == []


@pytest.fixture
def secondary_aip_location(
    make_location: LocationFactory, space: models.Space
) -> models.Location:
    """An AIP storage location in the local filesystem space, created on
    disk.
    """
    result = make_location(space, models.Location.AIP_STORAGE, relative_path="aips")
    pathlib.Path(result.full_path).mkdir()

    return result


@pytest.fixture
def deletion_request(
    make_event: EventFactory, package: models.Package, pipeline: models.Pipeline
) -> models.Event:
    """A pending request to delete the package."""
    return make_event(package, pipeline)


@pytest.mark.django_db
def test_move_request_fails_if_package_is_in_unexpected_state(
    admin_client: Client,
    package: models.Package,
    secondary_aip_location: models.Location,
) -> None:
    package.status = models.Package.MOVING
    package.save()

    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": secondary_aip_location.uuid},
    )

    assert response.status_code == 400
    assert json.loads(response.text) == {
        "error": True,
        "message": f"The file must be in an {models.Package.UPLOADED} state to be moved. Current state: {package.status}",
    }


@pytest.mark.django_db
def test_move_request_fails_if_location_uuid_is_missing(
    admin_client: Client, package: models.Package
) -> None:
    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        )
    )

    assert response.status_code == 400
    assert response.text == "All of these fields must be provided: location_uuid"


@pytest.mark.django_db
def test_move_request_fails_if_target_location_does_not_exist(
    admin_client: Client, package: models.Package
) -> None:
    location_uuid = uuid.uuid4()

    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": location_uuid},
    )

    assert response.status_code == 400
    assert json.loads(response.text) == {
        "error": True,
        "message": f"Location UUID {location_uuid} failed to return a location",
    }


@pytest.mark.django_db
def test_move_request_fails_if_target_location_is_origin_location(
    admin_client: Client, package: models.Package
) -> None:
    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": package.current_location.uuid},
    )

    assert response.status_code == 400
    assert json.loads(response.text) == {
        "error": True,
        "message": "New location must be different to the current location",
    }


@pytest.mark.django_db
def test_move_request_fails_if_target_location_purpose_does_not_match(
    admin_client: Client,
    package: models.Package,
    secondary_aip_location: models.Location,
) -> None:
    secondary_aip_location.purpose = models.Location.BACKLOG
    secondary_aip_location.save()

    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": secondary_aip_location.uuid},
    )

    assert response.status_code == 400
    assert json.loads(response.text) == {
        "error": True,
        "message": f"New location must have the same purpose as the current location - {package.current_location.purpose}",
    }


@pytest.mark.django_db
@mock.patch("django.db.models.query.QuerySet.update", return_value=0)
def test_move_request_fails_if_updating_package_status_fails(
    update: mock.Mock,
    admin_client: Client,
    package: models.Package,
    secondary_aip_location: models.Location,
) -> None:
    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": secondary_aip_location.uuid},
    )

    assert response.status_code == 400
    assert json.loads(response.text) == {
        "error": True,
        "message": f"The package must be in an {models.Package.UPLOADED} state to be moved. Current state: {package.status}",
    }
    update.assert_called_once_with(status=models.Package.MOVING)


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.locations.models.async_manager.AsyncManager.run_task"
)
def test_move_request_returns_asyncronous_task_url_in_response_headers(
    run_task: mock.Mock,
    admin_client: Client,
    package: models.Package,
    secondary_aip_location: models.Location,
) -> None:
    task_id = 1
    run_task.return_value = mock.Mock(id=task_id)

    response = admin_client.post(
        reverse(
            "move_request",
            kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
        ),
        {"location_uuid": secondary_aip_location.uuid},
    )
    assert response.status_code == 202

    assert not response.text
    assert response.headers["Location"] == reverse(
        "api_dispatch_detail",
        kwargs={"api_name": "v2", "resource_name": "async", "id": task_id},
    )


@pytest.mark.django_db
def test_review_aip_deletion_requires_permission(
    logged_in_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.APPROVE.value,
        "reason": "ok",
        "event_id": deletion_request.id,
    }

    resp = logged_in_client.post(
        url, data=json.dumps(data), content_type="application/json"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("decision", "reason", "expected_status", "expected_message", "expect_delete_call"),
    [
        (
            package_request.PackageRequestDecision.APPROVE.value,
            "Approved for deletion",
            models.Event.APPROVED,
            "Request approved: Package deleted successfully.",
            True,
        ),
        (
            package_request.PackageRequestDecision.REJECT.value,
            "Not this time",
            models.Event.REJECTED,
            "Request rejected, package still stored.",
            False,
        ),
    ],
    ids=["approve decision removes package", "reject decision leaves package stored"],
)
def test_review_aip_deletion_request(
    admin_client: Client,
    package: models.Package,
    deletion_request: models.Event,
    decision: str,
    reason: str,
    expected_status: str,
    expected_message: str,
    expect_delete_call: bool,
) -> None:
    event = deletion_request
    original_package_status = package.status
    package.status = models.Package.DEL_REQ
    package.save()
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )

    with mock.patch.object(
        models.Package, "delete_from_storage", return_value=(True, None)
    ) as delete_from_storage:
        resp = admin_client.post(
            url,
            data=json.dumps(
                {"decision": decision, "reason": reason, "event_id": event.id}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert json.loads(resp.text) == {"message": expected_message}

        if expect_delete_call:
            delete_from_storage.assert_called_once()
        else:
            delete_from_storage.assert_not_called()

        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == expected_status
        assert event.status_reason == reason

        if expect_delete_call:
            assert package.status == models.Package.DELETED
        else:
            assert package.status == original_package_status


@pytest.mark.django_db
def test_review_aip_deletion_request_reports_success_with_warning(
    admin_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    event = deletion_request
    package.status = models.Package.DEL_REQ
    package.save()
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.APPROVE.value,
        "reason": "Proceed with deletion",
        "event_id": event.id,
    }

    with mock.patch.object(
        models.Package, "delete_from_storage", return_value=(True, "LOCKSS warning")
    ) as delete_from_storage:
        resp = admin_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

    assert resp.status_code == 200
    assert json.loads(resp.text) == {
        "message": "Request approved: Package deleted successfully.",
        "detail": "LOCKSS warning",
    }

    delete_from_storage.assert_called_once()

    event.refresh_from_db()
    package.refresh_from_db()
    assert event.status == models.Event.APPROVED
    assert event.status_reason == data["reason"]
    assert package.status == models.Package.DELETED


@pytest.mark.django_db
def test_review_aip_deletion_request_reports_failure(
    admin_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    event = deletion_request
    package.status = models.Package.DEL_REQ
    package.save()
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.APPROVE.value,
        "reason": "Understood. Deleting!",
        "event_id": event.id,
    }

    with mock.patch.object(
        models.Package, "delete_from_storage", return_value=(False, "Disk error")
    ) as delete_from_storage:
        resp = admin_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert resp.status_code == 200
        assert json.loads(resp.text) == {
            "error_message": "Package was not deleted from disk correctly: Disk error. Please contact an administrator or see logs for details."
        }

        delete_from_storage.assert_called_once()

        # Event and package statuses remain unchanged because of the error.
        # The reason and administrator have been recorded.
        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == models.Event.SUBMITTED
        assert package.status == models.Package.DEL_REQ
        assert event.status_reason == data["reason"]
        assert event.admin_id is not None


@pytest.mark.django_db
def test_review_aip_deletion_request_allows_retry_after_failure(
    admin_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    event = deletion_request
    package.status = models.Package.DEL_REQ
    package.save()
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.APPROVE.value,
        "reason": "Sure! Deleting...",
        "event_id": event.id,
    }

    with mock.patch.object(
        models.Package,
        "delete_from_storage",
        side_effect=[(False, "Disk error"), (True, None)],
    ) as delete_from_storage:
        # This is the first attempt at approving the deletion request.
        resp = admin_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert resp.status_code == 200
        assert json.loads(resp.text) == {
            "error_message": "Package was not deleted from disk correctly: Disk error. Please contact an administrator or see logs for details."
        }

        # Event and package statuses remain unchanged because of the error.
        # The reason and administrator have been recorded.
        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == models.Event.SUBMITTED
        assert package.status == models.Package.DEL_REQ
        assert event.status_reason == data["reason"]
        assert event.admin_id is not None

        # Try the approval again.
        second_response = admin_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        assert second_response.status_code == 200
        assert json.loads(second_response.text) == {
            "message": "Request approved: Package deleted successfully.",
        }

        # The event and package statuses have been updated.
        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == models.Event.APPROVED
        assert event.status_reason == data["reason"]
        assert package.status == models.Package.DELETED

        # Ensure that the execution logic was called twice.
        delete_from_storage.assert_called()
        assert delete_from_storage.call_count == 2


@pytest.mark.django_db
def test_review_aip_deletion_request_retry_success_includes_warning(
    admin_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    event = deletion_request
    package.status = models.Package.DEL_REQ
    package.save()
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.APPROVE.value,
        "reason": "Retry deletion",
        "event_id": event.id,
    }

    with mock.patch.object(
        models.Package,
        "delete_from_storage",
        side_effect=[(False, "Disk error"), (True, "LOCKSS warning")],
    ) as delete_from_storage:
        # The first attempt fails.
        resp = admin_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert resp.status_code == 200
        assert json.loads(resp.text) == {
            "error_message": "Package was not deleted from disk correctly: Disk error. Please contact an administrator or see logs for details."
        }

        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == models.Event.SUBMITTED
        assert package.status == models.Package.DEL_REQ
        assert event.status_reason == data["reason"]

        # The retry succeeds and returns the warning detail.
        second_resp = admin_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert second_resp.status_code == 200
        assert json.loads(second_resp.text) == {
            "message": "Request approved: Package deleted successfully.",
            "detail": "LOCKSS warning",
        }

        delete_from_storage.assert_called()
        assert delete_from_storage.call_count == 2

        event.refresh_from_db()
        package.refresh_from_db()
        assert event.status == models.Event.APPROVED
        assert event.status_reason == data["reason"]
        assert package.status == models.Package.DELETED


@pytest.mark.django_db
def test_review_aip_deletion_request_cannot_be_reviewed_twice(
    admin_client: Client, package: models.Package, deletion_request: models.Event
) -> None:
    event = deletion_request
    original_package_status = package.status
    url = reverse(
        "review_aip_deletion_request",
        kwargs={"api_name": "v2", "resource_name": "file", "uuid": package.uuid},
    )
    data = {
        "decision": package_request.PackageRequestDecision.REJECT.value,
        "reason": "We cannot delete it. Sorry",
        "event_id": event.id,
    }

    # The deletion request is rejected.
    resp = admin_client.post(
        url, data=json.dumps(data), content_type="application/json"
    )
    assert resp.status_code == 200
    assert json.loads(resp.text) == {
        "message": "Request rejected, package still stored."
    }

    # The event status has been updated, but the package status is unchanged.
    event.refresh_from_db()
    package.refresh_from_db()
    assert event.status == models.Event.REJECTED
    assert package.status == original_package_status

    # Attempt to reject the request again.
    resp = admin_client.post(
        url, data=json.dumps(data), content_type="application/json"
    )
    assert resp.status_code == 400
    assert json.loads(resp.text) == {
        "error_message": "This request is not pending review."
    }
