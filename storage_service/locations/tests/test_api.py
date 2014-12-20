
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
