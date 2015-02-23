
import json

from django.test import TestCase
from django.test.client import Client

from locations import models

class TestAPI(TestCase):

    fixtures = ['base.json', 'pipelines.json']

    def setUp(self):
        self.client = Client()

    def test_cant_move_from_non_existant_locations(self):
        data = {
            'origin_location': '/api/v2/location/dne1aacf-8492-4382-8ef3-262cc5420dne/',
            'files': [{'source': 'foo', 'destination': 'bar'}],
            'pipeline': '/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/',
        }
        response = self.client.post('/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/', data=json.dumps(data), content_type='application/json')
        # Verify error
        assert response.status_code == 404
        assert 'not a link to a valid Location' in response.content

    def test_cant_move_to_non_existant_locations(self):
        data = {
            'origin_location': '/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/',
            'files': [{'source': 'foo', 'destination': 'bar'}],
            'pipeline': '/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/',
        }
        response = self.client.post('/api/v2/location/dne086c8-232e-4b9e-bb03-98fbc7a7966a/', data=json.dumps(data), content_type='application/json')
        # Verify error
        assert response.status_code == 404

    def test_cant_move_from_disabled_locations(self):
        # Set origin location disabled
        models.Location.objects.filter(uuid='6e61aacf-8492-4382-8ef3-262cc5420259').update(enabled=False)
        # Send request
        data = {
            'origin_location': '/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/',
            'files': [{'source': 'foo', 'destination': 'bar'}],
            'pipeline': '/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/',
        }
        response = self.client.post('/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/', data=json.dumps(data), content_type='application/json')
        # Verify error
        assert response.status_code == 404
        assert 'not a link to a valid Location' in response.content

    def test_cant_move_to_disabled_locations(self):
        # Set posting to location disabled
        models.Location.objects.filter(uuid='213086c8-232e-4b9e-bb03-98fbc7a7966a').update(enabled=False)
        # Send request
        data = {
            'origin_location': '/api/v2/location/6e61aacf-8492-4382-8ef3-262cc5420259/',
            'files': [{'source': 'foo', 'destination': 'bar'}],
            'pipeline': '/api/v2/pipeline/b25f6b71-3ebf-4fcc-823c-1feb0a2553dd/',
        }
        response = self.client.post('/api/v2/location/213086c8-232e-4b9e-bb03-98fbc7a7966a/', data=json.dumps(data), content_type='application/json')
        # Verify error
        assert response.status_code == 404

    def test_file_data_returns_metadata_given_relative_path(self):
        path = 'test_sip/objects/file.txt'
        response = self.client.get('/api/v2/file/metadata/',
                                   {'relative_path': path})
        assert response.status_code == 200
        assert response['content-type'] == 'application/json'
        body = json.loads(response.content)
        assert body[0]['relative_path'] == path
        assert body[0]['fileuuid'] == '86bfde11-e2a1-4ee7-b98d-9556b5f05198'

    def test_file_data_returns_bad_response_with_no_accepted_parameters(self):
        response = self.client.post('/api/v2/file/metadata/')
        assert response.status_code == 400

    def test_file_data_returns_404_if_no_file_found(self):
        response = self.client.get('/api/v2/file/metadata/', {'fileuuid': 'nosuchfile'})
        assert response.status_code == 404

    def test_package_contents_returns_metadata(self):
        response = self.client.get('/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/')
        assert response.status_code == 200
        assert response['content-type'] == 'application/json'
        body = json.loads(response.content)
        assert body['success'] is True
        assert len(body['files']) == 1
        assert body['files'][0]['name'] == 'test_sip/objects/file.txt'

    def test_adding_package_files_returns_400_with_empty_post_body(self):
        response = self.client.put('/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/',
                                   data="", content_type="application/json")
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_post_body_is_not_json(self):
        response = self.client.put('/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/',
                                   data="not json!",
                                   content_type="application/json")
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_post_body_is_not_a_list(self):
        response = self.client.put('/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/',
                                   data="{}", content_type="application/json")
        assert response.status_code == 400

    def test_adding_package_files_returns_400_if_expected_fields_are_missing(self):
        body = [{
            "relative_path": "/dev/null"
        }]
        response = self.client.put('/api/v2/file/e0a41934-c1d7-45ba-9a95-a7531c063ed1/contents/',
                                   data=json.dumps(body),
                                   content_type="application/json")
        assert response.status_code == 400

    def test_adding_files_to_package_returns_200_for_empty_list(self):
        response = self.client.put('/api/v2/file/79245866-ca80-4f84-b904-a02b3e0ab621/contents/',
                                   data='[]', content_type="application/json")
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

        response = self.client.put('/api/v2/file/79245866-ca80-4f84-b904-a02b3e0ab621/contents/',
                                   data=json.dumps(body),
                                   content_type="application/json")
        assert response.status_code == 201
        assert p.file_set.count() == 2

    def test_removing_file_from_package(self):
        p = models.Package.objects.get(uuid="a59033c2-7fa7-41e2-9209-136f07174692")
        assert p.file_set.count() == 1

        response = self.client.delete('/api/v2/file/a59033c2-7fa7-41e2-9209-136f07174692/contents/')
        assert response.status_code == 204
        assert p.file_set.count() == 0
