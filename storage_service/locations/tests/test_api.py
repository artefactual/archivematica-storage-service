import base64
import json
import os
import shutil
import vcr

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.six.moves.urllib.parse import urlparse

from locations import models
from locations.api.sword.views import _parse_name_and_content_urls_from_mets_file
from . import TempDirMixin

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))


class TestSpaceAPI(TestCase):

    fixtures = ["base.json"]

    def setUp(self):
        user = User.objects.get(username="test")
        user.set_password("test")
        self.client.defaults["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(
            "test:test"
        )

    def test_requires_auth(self):
        del self.client.defaults["HTTP_AUTHORIZATION"]
        response = self.client.get(
            "/api/v2/space/7d20c992-bc92-4f92-a794-7161ff2cc08b/"
        )
        assert response.status_code == 401

    def test_create_space(self):
        data = {
            "access_protocol": "S3",
            "path": "",
            "staging_path": "/",
            # Specific to the S3 protocol.
            "endpoint_url": "http://127.0.0.1:12345",
            "access_key_id": "Cah4cae1",
            "secret_access_key": "Thu6Ahqu",
            "region": "us-west-2",
        }
        response = self.client.post(
            "/api/v2/space/", data=json.dumps(data), content_type="application/json"
        )
        response_data = json.loads(response.content)
        assert response.status_code == 201

        protocol_model = models.S3.objects.get(space_id=response_data["uuid"])
        assert protocol_model.endpoint_url == data["endpoint_url"]


class TestLocationAPI(TestCase):

    fixtures = ["base.json", "pipelines.json", "package.json"]

    def setUp(self):
        user = User.objects.get(username="test")
        user.set_password("test")
        self.client.defaults["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(
            "test:test"
        )

    def test_requires_auth(self):
        del self.client.defaults["HTTP_AUTHORIZATION"]
        response = self.client.post(
            "/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/"
        )
        assert response.status_code == 401

    def test_create_location(self):
        space = models.Space.objects.get(uuid="7d20c992-bc92-4f92-a794-7161ff2cc08b")
        data = {
            "space": "/api/v2/space/7d20c992-bc92-4f92-a794-7161ff2cc08b/",
            "description": "automated workflow",
            "relative_path": "automated-workflow/foo/bar",
            "purpose": "TS",
            "pipeline": ["/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/"],
        }

        response = self.client.post(
            "/api/v2/location/", data=json.dumps(data), content_type="application/json"
        )
        assert response.status_code == 201

        # Verify content
        body = json.loads(response.content)
        assert body["description"] == data["description"]
        assert body["purpose"] == data["purpose"]
        assert body["path"] == "{}{}".format(space.path, data["relative_path"])
        assert body["enabled"] is True
        assert data["pipeline"][0] in body["pipeline"]

        # Verify that the record was populated properly
        location = models.Location.objects.get(uuid=body["uuid"])
        assert location.purpose == data["purpose"]
        assert location.relative_path == data["relative_path"]
        assert location.description == data["description"]

    def test_create_default_location(self):
        """Test that a new created location can be marked as default.

        Storage Service allows users to define a location the default one for
        its purpose application-wise.

        In our fixtures we already have a TS added. We're going to add a new
        one and confirm that it can be marked as the new default.
        """
        new_default_ts_location = {
            "space": "/api/v2/space/7d20c992-bc92-4f92-a794-7161ff2cc08b/",
            "description": "new location",
            "relative_path": "new-location/foo/bar",
            "purpose": "TS",
            "pipeline": ["/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/"],
            "default": True,
        }

        def _get_default_ts():
            return self.client.get(
                "/api/v2/location/default/TS/", content_type="application/json"
            )

        response = _get_default_ts()
        assert response.status_code == 404

        # Create default location.
        response = self.client.post(
            "/api/v2/location/",
            data=json.dumps(new_default_ts_location),
            content_type="application/json",
        )
        body = json.loads(response.content)

        response = _get_default_ts()
        assert response.status_code == 302
        assert response.url == "http://testserver/api/v2/location/%s/" % (body["uuid"],)

    def test_cant_move_from_non_existant_locations(self):
        data = {
            "origin_location": "/api/v2/location/dne1aacf-8492-4382-8ef3-262cc5420dne/",
            "files": [{"source": "foo", "destination": "bar"}],
            "pipeline": "/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/",
        }
        response = self.client.post(
            "/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/",
            data=json.dumps(data),
            content_type="application/json",
        )
        # Verify error
        assert response.status_code == 404
        assert "not a link to a valid Location" in response.content

    def test_cant_move_to_non_existant_locations(self):
        data = {
            "origin_location": "/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/",
            "files": [{"source": "foo", "destination": "bar"}],
            "pipeline": "/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/",
        }
        response = self.client.post(
            "/api/v2/location/dne086c8-232e-4b9e-bb03-98fbc7a7966a/",
            data=json.dumps(data),
            content_type="application/json",
        )
        # Verify error
        assert response.status_code == 404

    def test_cant_move_from_disabled_locations(self):
        # Set origin location disabled
        models.Location.objects.filter(
            uuid="6e61aacf-8492-4382-8ef3-262cc5420259"
        ).update(enabled=False)
        # Send request
        data = {
            "origin_location": "/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/",
            "files": [{"source": "foo", "destination": "bar"}],
            "pipeline": "/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/",
        }
        response = self.client.post(
            "/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/",
            data=json.dumps(data),
            content_type="application/json",
        )
        # Verify error
        assert response.status_code == 404
        assert "not a link to a valid Location" in response.content

    def test_cant_move_to_disabled_locations(self):
        # Set posting to location disabled
        models.Location.objects.filter(
            uuid="213086c8-232e-4b9e-bb03-98fbc7a7966a"
        ).update(enabled=False)
        # Send request
        data = {
            "origin_location": "/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/",
            "files": [{"source": "foo", "destination": "bar"}],
            "pipeline": "/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/",
        }
        response = self.client.post(
            "/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/",
            data=json.dumps(data),
            content_type="application/json",
        )
        # Verify error
        assert response.status_code == 404


class TestPackageAPI(TempDirMixin, TestCase):

    fixtures = ["base.json", "package.json", "arkivum.json"]

    def setUp(self):
        super(TestPackageAPI, self).setUp()
        ss_internal = self.tmpdir / "ss-internal"
        ss_internal.mkdir()
        self.test_location = models.Location.objects.get(
            uuid="615103f0-0ee0-4a12-ba17-43192d1143ea"
        )
        # Set up locations with fixtures
        shutil.copy(os.path.join(FIXTURES_DIR, "working_bag.zip"), str(self.tmpdir))
        self.test_location.relative_path = FIXTURES_DIR[1:]
        self.test_location.save()
        models.Space.objects.filter(uuid="6fb34c82-4222-425e-b0ea-30acfd31f52e").update(
            path=str(self.tmpdir)
        )
        ss_int = models.Location.objects.get(purpose="SS")
        ss_int.relative_path = str(ss_internal)[1:]
        ss_int.save()
        # Set Arkivum package request ID
        models.Package.objects.filter(
            uuid="c0f8498f-b92e-4a8b-8941-1b34ba062ed8"
        ).update(
            misc_attributes={
                "arkivum_identifier": "2e75c8ad-cded-4f7e-8ac7-85627a116e39"
            }
        )

        user = User.objects.get(username="test")
        user.set_password("test")
        self.client.defaults["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(
            "test:test"
        )

    def test_requires_auth(self):
        del self.client.defaults["HTTP_AUTHORIZATION"]
        urls = [
            "/api/v2/file/metadata/",
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/",
            "/api/v2/file/6aebdb24-1b6b-41ab-b4a3-df9a73726a34/download/",
            "/api/v2/file/0d4e739b-bf60-4b87-bc20-67a379b28cea/extract_file/",
        ]
        # Get metadata
        for url in urls:
            response = self.client.get(url)
            assert response.status_code == 401

    def test_file_data_returns_metadata_given_relative_path(self):
        path = "test_sip/objects/file.txt"
        response = self.client.get("/api/v2/file/metadata/", {"relative_path": path})
        assert response.status_code == 200
        assert response["content-type"] == "application/json"
        body = json.loads(response.content)
        assert body[0]["relative_path"] == path
        assert body[0]["fileuuid"] == "86bfde11-e2a1-4ee7-b98d-9556b5f05198"

    def test_file_data_returns_bad_response_with_no_accepted_parameters(self):
        response = self.client.post("/api/v2/file/metadata/")
        assert response.status_code == 400

    def test_file_data_returns_404_if_no_file_found(self):
        response = self.client.get("/api/v2/file/metadata/", {"fileuuid": "nosuchfile"})
        assert response.status_code == 404

    def test_package_contents_returns_metadata(self):
        response = self.client.get(
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/"
        )
        assert response.status_code == 200
        assert response["content-type"] == "application/json"
        body = json.loads(response.content)
        assert body["success"] is True
        assert len(body["files"]) == 1
        assert body["files"][0]["name"] == "test_sip/objects/file.txt"

    def test_adding_package_files_returns_400_with_empty_post_body(self):
        response = self.client.put(
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_post_body_is_not_json(self):
        response = self.client.put(
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/",
            data="not json!",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_post_body_is_not_a_list(self):
        response = self.client.put(
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/",
            data="{}",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_expected_fields_are_missing(self):
        body = [{"relative_path": "/dev/null"}]
        response = self.client.put(
            "/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_adding_files_to_package_returns_200_for_empty_list(self):
        response = self.client.put(
            "/api/v2/file/79245866-ca80-4f84-b904-a02b3e0ab621/contents/",
            data="[]",
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_adding_files_to_package(self):
        p = models.Package.objects.get(uuid="79245866-ca80-4f84-b904-a02b3e0ab621")
        assert p.file_set.count() == 0

        body = [
            {
                "relative_path": "empty-transfer-79245866-ca80-4f84-b904-a02b3e0ab621/1.txt",
                "fileuuid": "7bffcce7-63f5-4b2e-af57-d266bfa2e3eb",
                "accessionid": "",
                "sipuuid": "79245866-ca80-4f84-b904-a02b3e0ab621",
                "origin": "36398145-6e49-4b5b-af02-209b127f2726",
            },
            {
                "relative_path": "empty-transfer-79245866-ca80-4f84-b904-a02b3e0ab621/2.txt",
                "fileuuid": "152be912-819f-49c4-968f-d5ce959c1cb1",
                "accessionid": "",
                "sipuuid": "79245866-ca80-4f84-b904-a02b3e0ab621",
                "origin": "36398145-6e49-4b5b-af02-209b127f2726",
            },
        ]

        response = self.client.put(
            "/api/v2/file/79245866-ca80-4f84-b904-a02b3e0ab621/contents/",
            data=json.dumps(body),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert p.file_set.count() == 2

    def test_removing_file_from_package(self):
        p = models.Package.objects.get(uuid="a59033c2-7fa7-41e2-9209-136f07174692")
        assert p.file_set.count() == 1

        response = self.client.delete(
            "/api/v2/file/a59033c2-7fa7-41e2-9209-136f07174692/contents/"
        )
        assert response.status_code == 204
        assert p.file_set.count() == 0

    def test_download_compressed_package(self):
        """ It should return the package. """
        response = self.client.get(
            "/api/v2/file/6aebdb24-1b6b-41ab-b4a3-df9a73726a34/download/"
        )
        assert response.status_code == 200
        assert response["content-type"] == "application/zip"
        assert (
            response["content-disposition"] == 'attachment; filename="working_bag.zip"'
        )

    def test_download_uncompressed_package(self):
        """ It should tar a package before downloading. """
        response = self.client.get(
            "/api/v2/file/0d4e739b-bf60-4b87-bc20-67a379b28cea/download/"
        )
        assert response.status_code == 200
        assert response["content-type"] == "application/x-tar"
        assert (
            response["content-disposition"] == 'attachment; filename="working_bag.tar"'
        )
        content = "".join(response.streaming_content)  # Convert to one string
        assert "bag-info.txt" in content
        assert "bagit.txt" in content
        assert "manifest-md5.txt" in content
        assert "tagmanifest-md5.txt" in content
        assert "test.txt" in content

    def test_download_lockss_chunk_incorrect(self):
        """ It should default to the local path if a chunk ID is provided but package isn't in LOCKSS. """
        response = self.client.get(
            "/api/v2/file/0d4e739b-bf60-4b87-bc20-67a379b28cea/download/",
            data={"chunk_number": 1},
        )
        assert response.status_code == 200
        assert response["content-type"] == "application/x-tar"
        assert (
            response["content-disposition"] == 'attachment; filename="working_bag.tar"'
        )
        content = "".join(response.streaming_content)  # Convert to one string
        assert "bag-info.txt" in content
        assert "bagit.txt" in content
        assert "manifest-md5.txt" in content
        assert "tagmanifest-md5.txt" in content
        assert "test.txt" in content

    def test_download_package_not_exist(self):
        """ It should return 404 for a non-existant package. """
        response = self.client.get(
            "/api/v2/file/dnednedn-edne-dned-nedn-ednednednedn/download/",
            data={"chunk_number": 1},
        )
        assert response.status_code == 404

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "arkivum_update_package_status.yaml"
        )
    )
    def test_download_package_arkivum_not_available(self):
        """ It should return 202 if the file is in Arkivum but only on tape. """
        response = self.client.get(
            "/api/v2/file/c0f8498f-b92e-4a8b-8941-1b34ba062ed8/download/"
        )
        assert response.status_code == 202
        j = json.loads(response.content)
        assert j["error"] is False
        assert (
            j["message"]
            == "File is not locally available.  Contact your storage administrator to fetch it."
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "api_download_package_arkivum_error.yaml"
        )
    )
    def test_download_package_arkivum_error(self):
        """ It should return 502 error from Arkivum. """
        response = self.client.get(
            "/api/v2/file/c0f8498f-b92e-4a8b-8941-1b34ba062ed8/download/"
        )
        assert response.status_code == 502
        j = json.loads(response.content)
        assert j["error"] is True
        assert "Error" in j["message"] and "Arkivum" in j["message"]

    def test_download_file_no_path(self):
        """ It should return 400 Bad Request """
        response = self.client.get(
            "/api/v2/file/0d4e739b-bf60-4b87-bc20-67a379b28cea/extract_file/"
        )
        assert response.status_code == 400
        assert "relative_path_to_file" in response.content

    def test_download_file_from_compressed(self):
        """ It should extract and return the file. """
        response = self.client.get(
            "/api/v2/file/6aebdb24-1b6b-41ab-b4a3-df9a73726a34/extract_file/",
            data={"relative_path_to_file": "working_bag/data/test.txt"},
        )
        assert response.status_code == 200
        assert response["content-type"] == "text/plain"
        assert response["content-disposition"] == 'attachment; filename="test.txt"'
        content = "".join(response.streaming_content)  # Convert to one string
        assert content == "test"

    def test_download_file_from_uncompressed(self):
        """ It should return the file. """
        response = self.client.get(
            "/api/v2/file/0d4e739b-bf60-4b87-bc20-67a379b28cea/extract_file/",
            data={"relative_path_to_file": "working_bag/data/test.txt"},
        )
        assert response.status_code == 200
        assert response["content-type"] == "text/plain"
        assert response["content-disposition"] == 'attachment; filename="test.txt"'
        content = "".join(response.streaming_content)  # Convert to one string
        assert content == "test"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "arkivum_update_package_status.yaml"
        )
    )
    def test_download_file_arkivum_not_available(self):
        """ It should return 202 if the file is in Arkivum but only on tape. """
        response = self.client.get(
            "/api/v2/file/c0f8498f-b92e-4a8b-8941-1b34ba062ed8/extract_file/",
            data={"relative_path_to_file": "working_bag/data/test.txt"},
        )
        assert response.status_code == 202
        j = json.loads(response.content)
        assert j["error"] is False
        assert (
            j["message"]
            == "File is not locally available.  Contact your storage administrator to fetch it."
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "api_download_package_arkivum_error.yaml"
        )
    )
    def test_download_file_arkivum_error(self):
        """ It should return 502 error from Arkivum. """
        response = self.client.get(
            "/api/v2/file/c0f8498f-b92e-4a8b-8941-1b34ba062ed8/extract_file/",
            data={"relative_path_to_file": "working_bag/data/test.txt"},
        )
        assert response.status_code == 502
        j = json.loads(response.content)
        assert j["error"] is True
        assert "Error" in j["message"] and "Arkivum" in j["message"]


class TestSwordAPI(TestCase):
    def test_removes_forward_slash_parse_fedora_mets(self):
        """ It should remove forward slashes in the deposit name and all
        filenames extracted from a Fedora METS file.
        """
        fedora_mets_path = os.path.join(FIXTURES_DIR, "fedora_mets_slash.xml")
        mets_parse = _parse_name_and_content_urls_from_mets_file(fedora_mets_path)
        fileobjs = mets_parse["objects"]
        assert "/" not in mets_parse["deposit_name"]
        assert len(fileobjs) > 0
        for fileobj in fileobjs:
            assert "/" not in fileobj["filename"]


class TestPipelineAPI(TestCase):

    fixtures = ["base.json"]

    def setUp(self):
        user = User.objects.get(username="test")
        user.set_password("test")
        self.client.defaults["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(
            "test:test"
        )

    def test_pipeline_create(self):
        data = {
            "uuid": "34988712-ba32-4a07-a8a8-022e8482b66c",
            "description": "My pipeline",
            "remote_name": "https://archivematica-dashboard:8080",
            "api_key": "test",
            "api_username": "test",
        }
        response = self.client.post(
            "/api/v2/pipeline/", data=json.dumps(data), content_type="application/json"
        )
        assert response.status_code == 201

        pipeline = models.Pipeline.objects.get(uuid=data["uuid"])
        pipeline.parse_and_fix_url(pipeline.remote_name) == urlparse(
            data["remote_name"]
        )

        # When undefined the remote_name field should be populated after the
        # REMOTE_ADDR header.
        data["uuid"] = "54adc4b8-7f2f-474a-ba22-6e3792a92734"
        del data["remote_name"]
        response = self.client.post(
            "/api/v2/pipeline/",
            data=json.dumps(data),
            content_type="application/json",
            REMOTE_ADDR="192.168.0.10",
        )
        assert response.status_code == 201
        pipeline = models.Pipeline.objects.get(uuid=data["uuid"])
        pipeline.parse_and_fix_url(pipeline.remote_name) == urlparse(
            "http://192.168.0.10"
        )
