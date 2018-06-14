import imp
import json
import os
import pprint
import pydoc

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import LiveServerTestCase
from tastypie.models import ApiKey

from locations import models
from locations.api.beta import api

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))

SERVER_PATH = api.get_dflt_server_path()
API_PATH_PREFIX = '/api/beta/'


class TestBetaAPIClient(LiveServerTestCase):

    fixtures = ['base.json', 'pipelines.json', 'package.json', 'files.json']

    def setUp(self):
        self.username = 'test'
        user = User.objects.get(username=self.username)
        self.api_key = str(ApiKey.objects.get(user=user)).split()[0]
        self.client.defaults['HTTP_AUTHORIZATION'] = 'ApiKey test:{}'.format(
            self.api_key)

        # Get the Python client code from the Storage Service API and load it
        # into a module dynamically
        response = self.client.get('{}client/'.format(API_PATH_PREFIX),
                                   content_type='application/json')
        client_dict = json.loads(response.content)
        client_python = client_dict['client']
        client_module = imp.new_module('client')
        exec client_python in client_module.__dict__
        self.client_module = client_module

    @property
    def url(self):
        return self.live_server_url.rstrip('/') + '/'

    def _test_space_client(self):
        client = self.client_module.ArchivematicaStorageServiceApiClient(
            self.username, self.api_key, self.url)

        # Get all spaces
        ret = client.space.get_many()
        assert ret['paginator']['count'] == 1
        space = ret['items'][0]
        assert space['resource_uri'] == (
            '/api/beta/spaces/7d20c992-bc92-4f92-a794-7161ff2cc08b/')
        assert space['verified'] is False
        assert space['id'] == 1
        assert space['staging_path'] == ''
        assert space['uuid'] == '7d20c992-bc92-4f92-a794-7161ff2cc08b'
        assert space['access_protocol'] == u'FS'
        assert space['used'] == 0
        assert space['last_verified'] is None
        assert space['size'] is None
        assert space['path'] == '/'

        space_docs = get_docs(client.space)
        print(space_docs)

        # Get a single space
        ret = client.space.get(space['uuid'])
        assert ret == space

        # Create a space
        # ret = client.space.create(
        #     'FS', '/var/archivematica/storage_service', path='/')
        # pprint.pprint(ret)

        # Avoiding flake8 warnings:
        pprint.pprint('stuff')
        my_models = models

    def _test_client_docs(self):
        client_cls = self.client_module.ArchivematicaStorageServiceApiClient
        client = client_cls(self.username, self.api_key, self.url)
        client_docs = get_docs(client_cls)
        assert ('class ArchivematicaStorageServiceApiClient(BaseClient)' in
                client_docs)
        assert ('Archivematica Storage Service API version beta client' in
                client_docs)
        assert ('An API for the Archivematica Storage Service.' in
                client_docs)
        assert ('The following instance attributes allow interaction with the'
                ' resources that the' in client_docs)

        space_docs = get_docs(client.space)
        assert 'Provides access to the space resource' in space_docs
        assert ('create(self, access_protocol, staging_path, path=None,'
                ' size=None)' in space_docs)
        assert ('get_many(self, items_per_page=10, order_by_attribute=None,'
                ' order_by_direction=None, order_by_subattribute=None, page=1)'
                in space_docs)
        assert 'search(self, query, paginator=None)' in space_docs
        assert 'update(self, pk, staging_path, path=None, size=None)' in space_docs

        package_docs = get_docs(client.package)
        assert 'get_many(self, ' in package_docs
        assert 'get(self, ' in package_docs
        assert 'search(self, ' in package_docs
        # Package resource is read-only so client has no mutating methods:
        assert 'update(self, ' not in package_docs
        assert 'create(self, ' not in package_docs
        assert 'delete(self, ' not in package_docs

    def test_client(self):
        self._test_client_docs()
        self._test_space_client()


def get_docs(thing):
    return pydoc.plain(pydoc.render_doc(thing))
