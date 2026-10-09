import os
import pathlib
import shutil
import uuid
from unittest import mock

import pytest
from django.core.management import call_command

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.dspace import DSpace

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def dspace_fixtures(db: None) -> None:
    call_command(
        "loaddata",
        *[str(FIXTURES_DIR / name) for name in ["base.json", "dspace.json"]],
        verbosity=0,
    )


@pytest.fixture
def dspace(dspace_fixtures: None) -> DSpace:
    return DSpace.objects.get(id=1)


def test_has_required_attributes(dspace: DSpace) -> None:
    assert dspace.sd_iri
    assert dspace.user
    assert dspace.password
    assert dspace.sword_connection is None


@mock.patch(
    "httplib2.Http.request",
    side_effect=[
        (mock.Mock(status=200), ""),
        (
            mock.Mock(status=200),
            """
            <service xmlns="http://www.w3.org/2007/app" xmlns:atom="http://www.w3.org/2005/Atom">
                <workspace>
                    <atom:title type="text">DSpace at My University</atom:title>
                    <collection href="http://demo.dspace.org/swordv2/collection/123456789/2">
                        <atom:title type="text">Test collection</atom:title>
                        <collectionPolicy xmlns="http://purl.org/net/sword/terms/">Short license text</collectionPolicy>
                        <mediation xmlns="http://purl.org/net/sword/terms/">true</mediation>
                    </collection>
                </workspace>
                <version xmlns="http://purl.org/net/sword/terms/">2.0</version>
            </service>
            """,
        ),
    ],
)
def test_get_sword_connection(_request: mock.MagicMock, dspace: DSpace) -> None:
    assert dspace.sword_connection is None
    dspace._get_sword_connection()
    assert dspace.sword_connection is not None
    # Format is [ ( 'string', [collections] )]
    assert dspace.sword_connection.workspaces[0][1][0].title == "Test collection"


def test_get_metadata(dspace: DSpace, tmp_path: pathlib.Path) -> None:
    """It should fetch DC metadata from AIP."""
    shutil.copy(os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(tmp_path))
    ret = dspace._get_metadata(
        str(tmp_path / "small_compressed_bag.zip"),
        uuid.UUID("1056123d-8a16-49c2-ac51-8e5fa367d8b5"),
    )
    assert len(ret) == 6
    assert ret["dcterms_title"] == "Yamani Weapons"
    assert ret["dcterms_description.abstract"] == "Glaives are cool"
    assert ret["dcterms_contributor.author"] == "Keladry of Mindelan"
    assert ret["dcterms_date.issued"] == "2016"
    assert ret["dcterms_rights.copyright"] == "Public Domain"
    assert ret["dcterms_relation.ispartofseries"] == "None"


def test_split_package_zip(dspace: DSpace, tmp_path: pathlib.Path) -> None:
    """It should split a package into objects and metadata using ZIP."""
    # Setup
    shutil.copy(os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(tmp_path))
    path = str(tmp_path / "small_compressed_bag.zip")
    # Test
    split_paths = dspace._split_package(path)
    # Verify
    assert len(split_paths) == 2
    assert str(tmp_path / "objects.zip") in split_paths
    assert (tmp_path / "objects.zip").is_file()
    assert str(tmp_path / "metadata.zip") in split_paths
    assert (tmp_path / "metadata.zip").is_file()


def test_split_package_7z(dspace: DSpace, tmp_path: pathlib.Path) -> None:
    """It should split a package into objects and metadata using 7Z."""
    shutil.copy(os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(tmp_path))
    path = str(tmp_path / "small_compressed_bag.zip")
    dspace.archive_format = dspace.ARCHIVE_FORMAT_7Z
    # Test
    split_paths = dspace._split_package(path)
    # Verify
    assert len(split_paths) == 2
    assert str(tmp_path / "objects.7z") in split_paths
    assert (tmp_path / "objects.7z").is_file()
    assert str(tmp_path / "metadata.7z") in split_paths
    assert (tmp_path / "metadata.7z").is_file()


@mock.patch(
    "httplib2.Http.request",
    side_effect=[
        (mock.Mock(status=200), ""),
        (mock.Mock(status=200), ""),
        (
            mock.MagicMock(status=201),
            """
            <entry xmlns="http://www.w3.org/2005/Atom">
                <id>http://demo.dspace.org/swordv2/edit/86</id>
                <link href="http://demo.dspace.org/swordv2/edit/86" rel="edit" />
                <link href="http://demo.dspace.org/swordv2/edit/86" rel="http://purl.org/net/sword/terms/add" />
                <link href="http://demo.dspace.org/swordv2/edit-media/86.atom" rel="edit-media" type="application/atom+xml; type=feed" />
                <link href="http://demo.dspace.org/swordv2/statement/86.rdf" rel="http://purl.org/net/sword/terms/statement" type="application/rdf+xml" />
                <link href="http://demo.dspace.org/swordv2/statement/86.atom" rel="http://purl.org/net/sword/terms/statement" type="application/atom+xml; type=feed" />
                <link href="http://localhost:8080/xmlui/submit?workspaceID=86" rel="alternate" />
            </entry>
            """,
        ),
        (
            mock.MagicMock(status=201),
            """
            <entry xmlns="http://www.w3.org/2005/Atom">
                <id>http://demo.dspace.org/swordv2/edit/86</id>
                <link href="http://demo.dspace.org/swordv2/edit/86" rel="edit" />
                <link href="http://demo.dspace.org/swordv2/edit/86" rel="http://purl.org/net/sword/terms/add" />
                <link href="http://demo.dspace.org/swordv2/edit-media/86.atom" rel="edit-media" type="application/atom+xml; type=feed" />
                <link href="http://demo.dspace.org/swordv2/statement/86.rdf" rel="http://purl.org/net/sword/terms/statement" type="application/rdf+xml" />
                <link href="http://demo.dspace.org/swordv2/statement/86.atom" rel="http://purl.org/net/sword/terms/statement" type="application/atom+xml; type=feed" />
            </entry>
            """,
        ),
        (
            mock.MagicMock(status=200),
            """
            <feed xmlns="http://www.w3.org/2005/Atom">
                <entry>
                    <id>http://demo.dspace.org/xmlui/bitstream/123456789/35/1/sword-2016-08-10T19:25:00.original.xml</id>
                    <category term="http://purl.org/net/sword/terms/originalDeposit" scheme="http://purl.org/net/sword/terms/" label="Original Deposit" />
                </entry>
            </feed>
            """,
        ),
    ],
)
@mock.patch(
    "requests.post",
    side_effect=[mock.Mock(status_code=201), mock.Mock(status_code=201)],
)
def test_move_from_ss(
    _requests_post: mock.MagicMock,
    _request: mock.MagicMock,
    dspace: DSpace,
    tmp_path: pathlib.Path,
) -> None:
    # Create test.txt
    (tmp_path / "test.txt").open("w").write("test file\n")
    package = models.Package.objects.get(uuid="1056123d-8a16-49c2-ac51-8e5fa367d8b5")
    shutil.copy(os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(tmp_path))
    path = str(tmp_path / "small_compressed_bag.zip")

    # Upload
    dspace.move_from_storage_service(path, "irrelevent", package=package)

    # Verify
    assert package.current_path == "http://demo.dspace.org/swordv2/statement/86.atom"
    assert package.misc_attributes["handle"] == "123456789/35"
    # FIXME How to verify?
