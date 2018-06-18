import json
import os
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils.dateparse import parse_datetime
from tastypie.models import ApiKey

from locations import models
from locations.api.beta import api
from locations.api.beta.remple import Resources

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))


SERVER_PATH = api.get_dflt_server_path()
API_PATH_PREFIX = '/api/beta/'


class TestBetaAPI(TestCase):

    fixtures = ['base.json', 'pipelines.json', 'package.json', 'files.json']

    def setUp(self):
        user = User.objects.get(username='test')
        api_key = str(ApiKey.objects.get(user=user)).split()[0]
        self.client.defaults['HTTP_AUTHORIZATION'] = 'ApiKey test:{}'.format(api_key)

    def test_auth(self):
        original_auth = self.client.defaults['HTTP_AUTHORIZATION']
        response = self.client.get('{}files/'.format(API_PATH_PREFIX),
                                   content_type='application/json')
        assert response.status_code == 200
        self.client.defaults['HTTP_AUTHORIZATION'] = 'monkeys'
        response = self.client.get('{}files/'.format(API_PATH_PREFIX),
                                   content_type='application/json')
        assert response.status_code == 403
        self.client.defaults['HTTP_AUTHORIZATION'] = original_auth

    def test_get_many_files(self):

        known_files = {f.uuid: f for f in models.File.objects.all()}
        assert known_files
        known_file_count = len(known_files)
        response = self.client.get('{}files/'.format(API_PATH_PREFIX),
                                   content_type='application/json')
        assert response.status_code == 200
        fetched_files = json.loads(response.content)
        assert fetched_files['paginator']['count'] == known_file_count
        fetched_files = {f['uuid']: f for f in fetched_files['items']}
        for file_uuid, file_dict in fetched_files.items():
            file_instance = known_files[file_uuid]
            for attr in ('accessionid',
                         'checksum',
                         'id',
                         'name',
                         'origin',
                         'source_id',
                         'source_package',
                         'stored',
                         'uuid',
                         'size',
                         'format_name',
                         'pronom_id',
                         'normalized',
                         'valid',):
                assert file_dict[attr] == getattr(file_instance, attr)
            assert file_dict['resource_uri'] == Resources.get_resource_uri(
                SERVER_PATH, 'files', file_uuid)
            if file_instance.package:
                assert file_dict['package'] == Resources.get_resource_uri(
                    SERVER_PATH, 'packages', file_instance.package.uuid)

    def test_files_search(self):
        """Test searching over file resources."""

        # Search for files with PRONOM id x-fmt/111.
        known_files = {f.uuid: f for f in models.File.objects.all()}
        known_matches = [f for f in known_files.values()
                         if f.pronom_id == 'x-fmt/111']
        query = {'query': {'filter': ['pronom_id', '=', 'x-fmt/111']}}
        response = self.client.post('{}files/search/'.format(API_PATH_PREFIX),
                                    json.dumps(query),
                                    content_type='application/json')
        assert response.status_code == 200
        response = json.loads(response.content)
        assert sorted([f['uuid'] for f in response['items']]) == sorted(
            [f.uuid for f in known_matches])

        # Count the number of files with PRONOM id fmt/19 that were ingested
        # between 2015-12-16 and 2015-12-17. Use ISO timezones in search terms.
        fmt = 'fmt/19'
        max_dt_iso = '2015-12-17T11:59:59+00:00'
        min_dt_iso = '2015-12-16T00:00:00+00:00'
        max_dt = parse_datetime(max_dt_iso)
        min_dt = parse_datetime(min_dt_iso)
        known_matches = models.File.objects\
            .filter(pronom_id__exact=fmt)\
            .filter(ingestion_time__lte=max_dt)\
            .filter(ingestion_time__gte=min_dt)
        assert len(known_matches) == 2
        query = {'query': {'filter': [
            'and', [['pronom_id', '=', fmt],
                    ['ingestion_time', '<=', max_dt_iso],
                    ['ingestion_time', '>=', min_dt_iso]]]}}
        response = self.client.post('{}files/search/'.format(API_PATH_PREFIX),
                                    json.dumps(query),
                                    content_type='application/json')
        assert response.status_code == 200
        response = json.loads(response.content)
        assert response['paginator']['count'] == 2
        assert sorted([f['uuid'] for f in response['items']]) == sorted(
            [f.uuid for f in known_matches])

        # Count the number of files with PRONOM id fmt/19 that were ingested
        # between 2015-12-16 and 2015-12-17. Use 'Z' for UTC timezone.
        max_dt_iso = '2015-12-17T11:59:59Z'
        min_dt_iso = '2015-12-16T00:00:00Z'
        max_dt = parse_datetime(max_dt_iso)
        min_dt = parse_datetime(min_dt_iso)
        query = {'query': {'filter': [
            'and', [['pronom_id', '=', fmt],
                    ['ingestion_time', '<=', max_dt_iso],
                    ['ingestion_time', '>=', min_dt_iso]]]}}
        response = self.client.post('{}files/search/'.format(API_PATH_PREFIX),
                                    json.dumps(query),
                                    content_type='application/json')
        assert response.status_code == 200
        response = json.loads(response.content)
        assert response['paginator']['count'] == 2
        assert sorted([f['uuid'] for f in response['items']]) == sorted(
            [f.uuid for f in known_matches])

        # Search files based on the type of the package that they belong to:
        # relational search.
        files_in_aips = models.File.objects.filter(package__package_type='AIP')
        query = {'query': {'filter': ['package', 'package_type', '=', 'AIP']}}
        response = self.client.post('{}files/search/'.format(API_PATH_PREFIX),
                                    json.dumps(query),
                                    content_type='application/json')
        assert response.status_code == 200
        response = json.loads(response.content)
        assert response['paginator']['count'] == len(files_in_aips)
        assert sorted([f['uuid'] for f in response['items']]) == sorted(
            [f.uuid for f in files_in_aips])

    def test_mutate_location(self):
        """Test creation, updating and deletion of a location."""

        # 1. Create a new location
        existing_locations = models.Location.objects.all()
        response = self.client.get(
            '{}locations/'.format(API_PATH_PREFIX), content_type='application/json')
        assert response.status_code == 200
        fetched_locations = json.loads(response.content)
        assert sorted(l.uuid for l in existing_locations) == sorted(
            l['uuid'] for l in fetched_locations['items'])
        first_pipeline = models.Pipeline.objects.first()
        pipeline_uri = Resources.get_resource_uri(
            SERVER_PATH, 'pipelines', first_pipeline.uuid)
        first_space = models.Space.objects.first()
        space_uri = Resources.get_resource_uri(
            SERVER_PATH, 'spaces', first_space.uuid)
        new_loc_descr = 'My new location'
        new_loc_purp = 'AS'
        new_loc_rel_path = (
            'var/archivematica/sharedDirectory/www/MyNewAIPsStore')
        new_location = {
            'description': new_loc_descr,
            'enabled': True,
            'pipeline': [pipeline_uri],  # list of AM pipeline URIs
            'purpose': new_loc_purp,
            'quota': None,
            'relative_path': new_loc_rel_path,
            'replicators': [],
            'space': space_uri  # URI of a Space
        }
        response = self.client.post('{}locations/'.format(API_PATH_PREFIX),
                                    json.dumps(new_location),
                                    content_type='application/json')
        assert response.status_code == 201
        new_location = json.loads(response.content)
        assert new_location['description'] == new_loc_descr
        assert new_location['purpose'] == new_loc_purp
        assert new_location['relative_path'] == new_loc_rel_path
        assert new_location['replicators'] == []
        for thing in new_location['pipeline']:
            assert_is_resource_uri(thing, 'pipelines')
        new_loc_uri = new_location['resource_uri']
        assert_is_resource_uri(new_loc_uri, 'locations')
        assert_is_resource_uri(new_location['space'], 'spaces')

        # 2.a. Update the location.
        updated_loc_descr = 'My new awesome transfer source location'
        updated_loc_purp = 'TS'
        updated_loc_rel_path = 'home'
        updated_location = {
            'description': updated_loc_descr,
            'enabled': True,
            'pipeline': [pipeline_uri],
            'purpose': updated_loc_purp,
            'quota': None,
            'relative_path': updated_loc_rel_path,
            'replicators': [],
            'space': space_uri
        }
        response = self.client.put(new_loc_uri,
                                   json.dumps(updated_location),
                                   content_type='application/json')
        assert response.status_code == 200
        updated_location = json.loads(response.content)
        assert updated_location['description'] == updated_loc_descr
        assert updated_location['purpose'] == updated_loc_purp
        assert updated_location['relative_path'] == updated_loc_rel_path
        assert updated_location['replicators'] == []
        assert updated_location['resource_uri'] == new_loc_uri
        for thing in updated_location['pipeline']:
            assert_is_resource_uri(thing, 'pipelines')
        assert_is_resource_uri(updated_location['resource_uri'], 'locations')
        assert_is_resource_uri(updated_location['space'], 'spaces')

        # 2.b. Invalid update attempt
        bad_loc_purp = 'QQ'
        bad_space_uuid = str(uuid4())
        bad_space_uri = Resources.get_resource_uri(
            SERVER_PATH, 'spaces', bad_space_uuid)
        bad_updated_location = {
            'description': updated_loc_descr,
            'enabled': True,
            'pipeline': [pipeline_uri],
            'purpose': bad_loc_purp,
            'quota': None,
            'relative_path': updated_loc_rel_path,
            'replicators': [],
            'space': bad_space_uri
        }
        bad_update_resp = self.client.put(new_loc_uri,
                                          json.dumps(bad_updated_location),
                                          content_type='application/json')
        assert bad_update_resp.status_code == 400
        bad_update_resp = json.loads(bad_update_resp.content)
        assert bad_update_resp['error']['purpose'].startswith(
            'Value must be one of: ')
        assert bad_update_resp['error']['space'] == (
            'There is no space with pk {}.'.format(bad_space_uuid))

        # 3. Delete the location
        response = self.client.delete(
            new_loc_uri, content_type='application/json')
        deleted_location = json.loads(response.content)
        assert response.status_code == 200
        assert deleted_location == updated_location
        response = self.client.get(
            updated_location['resource_uri'],
            content_type='application/json')
        assert response.status_code == 404
        nonexistent_location = json.loads(response.content)
        assert nonexistent_location['error'].startswith(
            'There is no location with uuid ')

    def test_mutate_space(self):
        """Test creation, updating and deletion of a space.

        Space is somewhat special in that its access protocol should be
        immutable after creation.
        """

        # 1. Create a new space
        existing_spaces = models.Space.objects.all()
        response = self.client.get(
            '{}spaces/'.format(API_PATH_PREFIX), content_type='application/json')
        assert response.status_code == 200
        fetched_spaces = json.loads(response.content)
        assert sorted(l.uuid for l in existing_spaces) == sorted(
            l['uuid'] for l in fetched_spaces['items'])
        new_space_acc_prot = 'FS'
        new_space_path = '/'
        new_space_staging_path = '/var/archivematica/storage_service'
        new_space = {
            'access_protocol': new_space_acc_prot,
            'path': new_space_path,
            'staging_path': new_space_staging_path,
            'size': None,
        }
        resp = self.client.post('{}spaces/'.format(API_PATH_PREFIX),
                                json.dumps(new_space),
                                content_type='application/json')
        assert resp.status_code == 201
        new_space = json.loads(resp.content)
        assert new_space['access_protocol'] == new_space_acc_prot
        assert new_space['path'] == new_space_path
        assert new_space['staging_path'] == new_space_staging_path
        new_space_uri = new_space['resource_uri']
        assert_is_resource_uri(new_space_uri, 'spaces')

        # 2.a. Update the space
        updated_space_path = '/abc'
        updated_space = {
            'path': updated_space_path,
            'staging_path': new_space_staging_path,
            'size': None,
        }
        response = self.client.put(new_space_uri,
                                   json.dumps(updated_space),
                                   content_type='application/json')
        assert response.status_code == 200
        updated_space = json.loads(response.content)
        assert updated_space['access_protocol'] == new_space_acc_prot
        assert updated_space['path'] == updated_space_path
        assert updated_space['staging_path'] == new_space_staging_path

        # 2.b. Can't update a space's access protocol
        updated_space = {
            'access_protocol': 'GPG',  # This is BAD
            'path': updated_space_path,
            'staging_path': new_space_staging_path,
            'size': 100,
        }
        resp = self.client.put(new_space_uri,
                               json.dumps(updated_space),
                               content_type='application/json')
        assert resp.status_code == 400
        resp = json.loads(resp.content)
        assert resp['error'] == (
            'The input field u\'access_protocol\' was not expected.')

    def test_get_create_update_data(self):
        """Test that the GET /<COLL>/new/ and /<COLL>/<UUID>/edit/ requests
        return the data needed to create new and edit existing resources.
        """

        # GET locations/new/ should return a dict containing resource URIs for
        # all locations, pipelines and spaces
        response = self.client.get('{}locations/new/'.format(API_PATH_PREFIX),
                                   content_type='application/json')
        create_data = json.loads(response.content)
        assert sorted(create_data.keys()) == sorted(
            ['locations', 'pipelines', 'spaces'])
        for resource_coll_name, value_list in create_data.items():
            for element in value_list:
                assert_is_resource_uri(element, resource_coll_name)

        # GET locations/<UUID>/edit/ should return a dict containing resource
        # URIs for all locations, pipelines and spaces
        aloc = models.Location.objects.first()
        response = self.client.get(
            '{}locations/{}/edit/'.format(API_PATH_PREFIX, aloc.uuid),
            content_type='application/json')
        edit_data = json.loads(response.content)
        assert edit_data['resource']['uuid'] == aloc.uuid
        assert sorted(edit_data['data'].keys()) == sorted(
            ['locations', 'pipelines', 'spaces'])
        for resource_coll_name, value_list in edit_data['data'].items():
            for element in value_list:
                assert_is_resource_uri(element, resource_coll_name)

    def test_new_search(self):
        """Test that the GET /<COLL>/new_search/ request return the data needed
        to perform a new search.
        """
        response = self.client.get(
            '{}locations/new_search/'.format(API_PATH_PREFIX),
            content_type='application/json')
        search_data = json.loads(response.content)
        search_params = search_data['search_parameters']
        assert 'attributes' in search_params
        assert 'relations' in search_params
        assert search_params['attributes']['pipeline'][
            'foreign_model'] == 'Pipeline'
        assert search_params['attributes']['pipeline'][
            'type'] == 'collection'
        assert search_params['attributes']['space'][
            'foreign_model'] == 'Space'
        assert search_params['attributes']['space'][
            'type'] == 'scalar'
        assert search_params['attributes']['quota'] == {}
        assert '=' in search_params['relations']
        assert 'regex' in search_params['relations']
        assert 'regexp' in search_params['relations']
        assert 'like' in search_params['relations']
        assert 'contains' in search_params['relations']
        assert '<=' in search_params['relations']

    def test_read_only_resources(self):
        for rsrc_coll in ('files', 'packages'):
            response = self.client.post(
                '{}{}/'.format(API_PATH_PREFIX, rsrc_coll),
                json.dumps({'foo': 'bar'}),
                content_type='application/json')
            payload = json.loads(response.content)
            assert response.status_code == 404
            assert payload['error'] == 'This resource is read-only.'


def assert_is_resource_uri(string, resource):
    _, _, xtrctd_rsrc, xtrctd_uuid = list(filter(None, string.split('/')))
    assert resource == xtrctd_rsrc
    recomposed = []
    parts = xtrctd_uuid.split('-')
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
    for part in parts:
        new_part = ''.join(c for c in part if c in '0123456789abcdef')
        recomposed.append(new_part)
    recomposed = '-'.join(recomposed)
    assert recomposed == xtrctd_uuid
