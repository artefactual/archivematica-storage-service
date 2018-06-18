import imp
import json
import os
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
    """Test the Beta API using the Python client module that is dynamically
    generated and served by the Beta API.
    """

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
        assert 'class SpaceClient(BaseClient)' in space_docs
        assert 'Access to the space resource' in space_docs
        # Get a single space
        ret = client.space.get(space['uuid'])
        assert ret == space

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
        assert 'Access to the space resource' in space_docs
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

    def _test_arkivum_client(self):
        """Test creating, updating and deleting an Arkivum Space using the API
        client.
        """
        client = self.client_module.ArchivematicaStorageServiceApiClient(
            self.username, self.api_key, self.url)

        # Get all spaces (hint: there are none)
        ret = client.arkivum_space.get_many()
        assert ret['paginator']['count'] == 0
        assert ret['items'] == []

        # Create a new space
        new_space = client.space.create(
            'FS', '/var/archivematica/storage_service', path='/')
        assert new_space['access_protocol'] == 'FS'
        assert new_space['path'] == '/'
        new_space_uri = new_space['resource_uri']

        # Get the client docs for creating a new Arkivum space
        arkivum_space_create_docs = get_docs(client.arkivum_space.create)
        assert ('create(self, host, space, remote_name=None, remote_user=None)'
                in arkivum_space_create_docs)
        assert ('host (str or unicode): Hostname of the Arkivum web instance.'
                in arkivum_space_create_docs)
        assert ('space (str or unicode; URI of a space resource)'
                in arkivum_space_create_docs)
        assert ('remote_name (str or unicode): Optional: Name or IP of the'
                ' remote machine' in arkivum_space_create_docs)
        assert ('remote_user (str or unicode): Optional: Username on the remote'
                ' machine' in arkivum_space_create_docs)

        # Create a new Arkivum space
        new_arkivum_space = client.arkivum_space.create(
            host='arkivum.example.com:8443',
            space=new_space_uri)
        assert new_arkivum_space['host'] == 'arkivum.example.com:8443'
        assert new_arkivum_space['space'] == new_space_uri
        # Note even though we passed None/null to the server, we get back the
        # empty string. This is maybe undesirable and is mixed up in Django's
        # behaviour related to ``null`` and ``blank`` on model fields.
        assert new_arkivum_space['remote_user'] == ''
        assert new_arkivum_space['remote_name'] == ''

        # Get the client docs for updating an Arkivum space.
        arkivum_space_update_docs = get_docs(client.arkivum_space.update)
        assert ('update(self, pk, host, space, remote_name=None,'
                ' remote_user=None)' in arkivum_space_update_docs)
        assert ('pk (int; database id): The primary key of the'
                ' arkivum_space' in arkivum_space_update_docs)
        assert ('host (str or unicode): Hostname of the Arkivum web instance'
                in arkivum_space_update_docs)
        assert ('space (str or unicode; URI of a space resource)'
                in arkivum_space_update_docs)
        assert ('remote_name (str or unicode): Optional: Name or IP of the'
                ' remote machine' in arkivum_space_update_docs)
        assert ('remote_user (str or unicode): Optional: Username on the remote'
                ' machine' in arkivum_space_update_docs)

        # Update the Arkivum space.
        updated_arkivum_space = client.arkivum_space.update(
            pk=new_arkivum_space['id'],
            host='arkivum.example.org:8889',
            space=new_space_uri,
            remote_user='jimmyjames')
        assert updated_arkivum_space['resource_uri'].startswith(
            '{}arkivumspaces/'.format(API_PATH_PREFIX))
        assert updated_arkivum_space['host'] == 'arkivum.example.org:8889'
        assert updated_arkivum_space['space'] == new_space_uri
        assert updated_arkivum_space['remote_user'] == 'jimmyjames'
        assert updated_arkivum_space['remote_name'] == ''

        # Get the clientn docs for deleting an Arkivum space.
        arkivum_space_delete_docs = get_docs(client.arkivum_space.delete)
        assert 'delete(self, pk)' in arkivum_space_delete_docs
        assert 'Delete an existing arkivum_space' in arkivum_space_delete_docs
        assert ('pk (int; database id): The primary key of the arkivum_space'
                in arkivum_space_delete_docs)

        # Delete the Arkivum space using the client.
        arkivum_space_orm_before = models.Arkivum.objects.filter(
            pk=new_arkivum_space['id']).first()
        assert arkivum_space_orm_before
        deleted_arkivum_space = client.arkivum_space.delete(
            pk=new_arkivum_space['id'])
        assert deleted_arkivum_space == updated_arkivum_space
        arkivum_space_orm_after = models.Arkivum.objects.filter(
            pk=new_arkivum_space['id']).first()
        assert not arkivum_space_orm_after

    def _test_other_client_subclasses(self):
        client = self.client_module.ArchivematicaStorageServiceApiClient(
            self.username, self.api_key, self.url)

        # Event resource
        event_docs = get_docs(client.event)
        assert ('Stores requests to modify packages that need admin approval.'
                in event_docs)
        assert 'get_many(' in event_docs
        assert 'create(' not in event_docs  # read-only

        # Callback resource
        callback_docs = get_docs(client.callback)
        assert ('Allows REST callbacks to be associated with specific Storage'
                ' Service events.' in callback_docs)
        assert 'get_many(' in callback_docs
        assert 'create(' not in callback_docs  # read-only

        # Fixity_log resource
        fixity_log_docs = get_docs(client.fixity_log)
        assert ('Stores fixity check success/failure and error details' in
                fixity_log_docs)
        assert 'get(' in fixity_log_docs
        assert 'get_many(' in fixity_log_docs
        assert 'search(' in fixity_log_docs
        assert 'create(' not in fixity_log_docs  # read-only

    def _test_location_client(self):
        """Test the location client, in particular its browse custom endpoint.
        """
        client = self.client_module.ArchivematicaStorageServiceApiClient(
            self.username, self.api_key, self.url)

        location_docs = get_docs(client.location)
        assert 'browse(self, pk, path=None)' in location_docs
        assert 'Browse a location' in location_docs
        assert ('Browse a location at the root (default) or at a supplied'
                ' path.' in location_docs)
        assert ('pk (str or unicode; UUID of a Location resource): UUID of the'
                ' location to' in location_docs)
        assert ('path (str or unicode): Path to browse within the Location'
                ' (optional).' in location_docs)
        assert ('dict: with key(s): "entries", "directories", "properties", if'
                ' request to' in location_docs)
        assert 'browse a location was successful.' in location_docs

        # Browse an AIP Storage location and assert that browsing it with the
        # beta client returns the same results as browsing via the V2 API.
        aip_store_loc = client.location.search(
            query={'filter': ['purpose', '=', 'AS']})['items'][0]
        beta_browse_ret = client.location.browse(aip_store_loc['uuid'])
        v2_browse_ret = self.client.get(
            '/api/v2/location/{}/browse/'.format(aip_store_loc['uuid']),
            content_type='application/json')
        v2_browse_ret = json.loads(v2_browse_ret.content)
        assert beta_browse_ret['entries'] == v2_browse_ret['entries']
        assert beta_browse_ret['directories'] == v2_browse_ret['directories']
        assert sorted(beta_browse_ret['properties'].keys()) == sorted(
            v2_browse_ret['properties'].keys())

    def _test_user_client(self):
        client = self.client_module.ArchivematicaStorageServiceApiClient(
            self.username, self.api_key, self.url)

        user_docs = get_docs(client.user)
        print(user_docs)
        assert ('create(self, password, username, email=None, first_name=None,'
                ' groups=None, is_active=None, is_staff=None,'
                ' is_superuser=None, last_name=None, user_permissions=None)'
                in user_docs)

        users = client.user.get_many()
        assert users['items'][0]['username'] == 'test'

        created_user = client.user.create(
            password='monkey123',
            username='monkey',
            email='monkey@gmail.com',
            first_name='Mon',
            last_name='Key')
        assert created_user['resource_uri'].startswith(
            '{}users/'.format(API_PATH_PREFIX))
        assert created_user['username'] == 'monkey'
        assert 'password' not in created_user['username']

    def test_client(self):
        self._test_client_docs()
        self._test_space_client()
        self._test_arkivum_client()
        self._test_other_client_subclasses()
        self._test_location_client()
        self._test_user_client()


def get_docs(thing):
    """Return a string representation of the output of ``help(thing)``."""
    return pydoc.plain(pydoc.render_doc(thing))
