import os
import pathlib
import shutil
import uuid
from unittest import mock

from django.test import TestCase
from locations import models

from . import TempDirMixin

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestDSpace(TempDirMixin, TestCase):
    fixture_files = ["base.json", "dspace.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def setUp(self):
        super().setUp()
        self.dspace_object = models.DSpace.objects.get(id=1)

    def test_has_required_attributes(self):
        assert self.dspace_object.sd_iri
        assert self.dspace_object.user
        assert self.dspace_object.password
        assert self.dspace_object.sword_connection is None

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
    def test_get_sword_connection(self, _request):
        assert self.dspace_object.sword_connection is None
        self.dspace_object._get_sword_connection()
        assert self.dspace_object.sword_connection is not None
        # Format is [ ( 'string', [collections] )]
        assert (
            self.dspace_object.sword_connection.workspaces[0][1][0].title
            == "Test collection"
        )

    def test_get_metadata(self):
        """It should fetch DC metadata from AIP."""
        shutil.copy(
            os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(self.tmpdir)
        )
        ret = self.dspace_object._get_metadata(
            str(self.tmpdir / "small_compressed_bag.zip"),
            uuid.UUID("1056123d-8a16-49c2-ac51-8e5fa367d8b5"),
        )
        assert len(ret) == 6
        assert ret["dcterms_title"] == "Yamani Weapons"
        assert ret["dcterms_description.abstract"] == "Glaives are cool"
        assert ret["dcterms_contributor.author"] == "Keladry of Mindelan"
        assert ret["dcterms_date.issued"] == "2016"
        assert ret["dcterms_rights.copyright"] == "Public Domain"
        assert ret["dcterms_relation.ispartofseries"] == "None"

    def test_split_package_zip(self):
        """It should split a package into objects and metadata using ZIP."""
        # Setup
        shutil.copy(
            os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(self.tmpdir)
        )
        path = str(self.tmpdir / "small_compressed_bag.zip")
        # Test
        split_paths = self.dspace_object._split_package(path)
        # Verify
        assert len(split_paths) == 2
        assert str(self.tmpdir / "objects.zip") in split_paths
        assert (self.tmpdir / "objects.zip").is_file()
        assert str(self.tmpdir / "metadata.zip") in split_paths
        assert (self.tmpdir / "metadata.zip").is_file()

    def test_split_package_7z(self):
        """It should split a package into objects and metadata using 7Z."""
        shutil.copy(
            os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(self.tmpdir)
        )
        path = str(self.tmpdir / "small_compressed_bag.zip")
        self.dspace_object.archive_format = self.dspace_object.ARCHIVE_FORMAT_7Z
        # Test
        split_paths = self.dspace_object._split_package(path)
        # Verify
        assert len(split_paths) == 2
        assert str(self.tmpdir / "objects.7z") in split_paths
        assert (self.tmpdir / "objects.7z").is_file()
        assert str(self.tmpdir / "metadata.7z") in split_paths
        assert (self.tmpdir / "metadata.7z").is_file()

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
    def test_move_from_ss(self, _requests_post, _request):
        # Create test.txt
        (self.tmpdir / "test.txt").open("w").write("test file\n")
        package = models.Package.objects.get(
            uuid="1056123d-8a16-49c2-ac51-8e5fa367d8b5"
        )
        shutil.copy(
            os.path.join(FIXTURES_DIR, "small_compressed_bag.zip"), str(self.tmpdir)
        )
        path = str(self.tmpdir / "small_compressed_bag.zip")

        # Upload
        self.dspace_object.move_from_storage_service(
            path, "irrelevent", package=package
        )

        # Verify
        assert (
            package.current_path == "http://demo.dspace.org/swordv2/statement/86.atom"
        )
        assert package.misc_attributes["handle"] == "123456789/35"
        # FIXME How to verify?
