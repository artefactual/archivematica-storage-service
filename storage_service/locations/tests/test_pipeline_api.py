import base64
import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils.six.moves.urllib.parse import urlparse

from locations import models

class TestPipelineAPI(TestCase):

    fixtures = ['base.json']

    def setUp(self):
        user = User.objects.get(username='test')
        user.set_password('test')
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Basic ' + base64.b64encode('test:test')

    def test_pipeline_create(self):
        data = {
            'uuid': '34988712-ba32-4a07-a8a8-022e8482b66c',
            'description': 'My pipeline',
            'remote_name': 'https://archivematica-dashboard:8080',
            'api_key': 'test',
            'api_username': 'test',
        }
        response = self.client.post('/api/v2/pipeline/',
                                    data=json.dumps(data),
                                    content_type='application/json')
        assert response.status_code == 201

        pipeline = models.Pipeline.objects.get(uuid=data['uuid'])
        pipeline.parse_and_fix_url() == urlparse(data['remote_name'])

        # When undefined the remote_name field should be populated after the
        # REMOTE_ADDR header.
        data['uuid'] = '54adc4b8-7f2f-474a-ba22-6e3792a92734'
        del data['remote_name']
        response = self.client.post('/api/v2/pipeline/',
                                    data=json.dumps(data),
                                    content_type='application/json',
                                    REMOTE_ADDR='192.168.0.10')
        assert response.status_code == 201
        pipeline = models.Pipeline.objects.get(uuid=data['uuid'])
        pipeline.parse_and_fix_url() == urlparse('http://192.168.0.10')