import os
import requests
import shutil
import vcr

from django.test import TestCase

from locations import models

import test_locs 
FIXTURES_READ_DIR = test_locs.FIXTURES_READ_DIR
FIXTURES_WRITE_DIR = test_locs.FIXTURES_WRITE_DIR
ARKIVUM_DIR = test_locs.ARKIVUM_WRITE_DIR

def get_pkg_uuid_path(package_uuid):
    tmp = package_uuid.replace('-', '')
    return os.path.join(*[tmp[i:i + 4] for i in range(0, len(tmp), 4)])


class TestArkivum(TestCase):

    fixtures = ['base.json', 'arkivum.json']

    def setUp(self):
        self.arkivum_object = models.Arkivum.objects.all()[0]
        self.arkivum_object.space.path = FIXTURES_READ_DIR
        self.arkivum_object.space.staging_path = FIXTURES_WRITE_DIR

        self.arkivum_object.space.save()

        package_uuid = 'c0f8498f-b92e-4a8b-8941-1b34ba062ed8'
        self.package = models.Package.objects.get(uuid=package_uuid)


        # Here we make sure that the test pointer file is where the package
        # expects it to be.
        self.package.pointer_file_location.space = self.arkivum_object.space

        self.package.pointer_file_location.relative_path = 'arkivum/storage_service'

        pointer_fname = 'pointer.' + package_uuid + '.xml'
        pointer_src_path = os.path.join(FIXTURES_READ_DIR, pointer_fname)


        # N.B. We can only write to user space... These need to be replaced
        # with write_dir where most approprate...

        pointer_dst_path = os.path.join(
            self.package.pointer_file_location.space.path,
            self.package.pointer_file_location.relative_path,
            get_pkg_uuid_path(package_uuid),
            pointer_fname)
        try:
            os.makedirs(os.path.dirname(pointer_dst_path))
        except OSError:
            pass

        shutil.copyfile(pointer_src_path, pointer_dst_path)
        self.uncompressed_package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        # Create filesystem to interact with
        os.mkdir(os.path.join(ARKIVUM_DIR, 'aips'))
        os.mkdir(os.path.join(ARKIVUM_DIR, 'ts'))
        with open(os.path.join(ARKIVUM_DIR, 'test.txt'), 'ab') as f:
            f.write('test.txt contents')

    def tearDown(self):
        shutil.rmtree(ARKIVUM_DIR)

    def test_has_required_attributes(self):
        assert self.arkivum_object.host
        # Both or neither of remote_user/remote_name
        assert bool(self.arkivum_object.remote_user) == bool(self.arkivum_object.remote_name)

    def test_browse(self):
        response = self.arkivum_object.browse(ARKIVUM_DIR)
        assert response
        assert set(response['directories']) == set(['aips', 'ts', 'storage_service'])
        assert set(response['entries']) == set(['aips', 'test.txt', 'ts', 'storage_service'])
        assert response['properties']['test.txt']['size'] == 17
        assert response['properties']['aips']['object count'] == 0
        assert response['properties']['ts']['object count'] == 0

    @vcr.use_cassette(os.path.join(FIXTURES_READ_DIR, 'vcr_cassettes', 'arkivum_delete.yaml'))
    def test_delete(self):
        # Verify exists
        url = 'https://' + self.arkivum_object.host + '/files/ts'
        response = requests.get(url, verify=False)
        assert 'unittest.txt' in [x['name'] for x in response.json()['files']]
        # Delete file
        self.arkivum_object.delete_path('/ts/unittest.txt')
        # Verify deleted
        url = 'https://' + self.arkivum_object.host + '/files/ts'
        response = requests.get(url, verify=False)
        assert 'unittest.txt' not in [x['name'] for x in response.json()['files']]

    
    @vcr.use_cassette(os.path.join(FIXTURES_READ_DIR, 'vcr_cassettes', 'arkivum_post_move_from_ss.yaml'))
    def test_post_move_from_ss(self):
        # POST to Arkivum about file
        self.arkivum_object.post_move_from_storage_service(
            os.path.join(FIXTURES_WRITE_DIR, 'working_bag.zip'),
            self.package.full_path,
            self.package)
        assert self.package.misc_attributes['arkivum_identifier'] == (
            'a09f9c18-df2b-474f-8c7f-50eb3dedba2d')

    '''
    @vcr.use_cassette(os.path.join(FIXTURES_READ_DIR, 'vcr_cassettes', 'arkivum_update_package_status.yaml'))
    def test_update_package_status_compressed(self):
        # Setup request_id
        self.package.misc_attributes.update({'arkivum_identifier': '2e75c8ad-cded-4f7e-8ac7-85627a116e39'})
        self.package.save()
        # Verify status is STAGING
        assert self.package.status == models.Package.STAGING
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.package)
        # Verify is still staged
        assert self.package.status == models.Package.STAGING
        # Test (response green)
        self.arkivum_object.update_package_status(self.package)
        # Verify UPLOADED
        assert self.package.status == models.Package.UPLOADED
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.package)
        # Verify what?
    '''

    @vcr.use_cassette(os.path.join(FIXTURES_READ_DIR, 'vcr_cassettes', 'arkivum_update_package_status_uncompressed.yaml'))
    def test_update_package_status_uncompressed(self):
        # Setup request_id
        self.uncompressed_package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        self.uncompressed_package.save()
        # Verify status is STAGING
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response Scheduled)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify is still staged
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify is still staged
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response green)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify UPLOADED
        assert self.uncompressed_package.status == models.Package.UPLOADED
