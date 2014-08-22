import os
import requests

from django.test import TestCase
import vcr

from locations import models


class TestDuracloud(TestCase):

    fixtures = ['initial_data.json', 'duracloud.json']

    def setUp(self):
        self.ds_object = models.Duracloud.objects.all()[0]

    def test_has_required_attributes(self):
        assert self.ds_object.host
        assert self.ds_object.user
        assert self.ds_object.password
        assert self.ds_object.duraspace

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss.yaml')
    def test_move_from_ss(self):
        # Create test.txt
        open('test.txt', 'w').write('test file\n')
        # Upload
        self.ds_object.move_from_storage_service('test.txt', '/ts/test.txt')
        # Unsure how to verify. Will raise exception if fails?
        # Cleanup
        os.remove('test.txt')
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/ts/test.txt', auth=auth)
        # Create test folder
        os.mkdir('test')
        os.mkdir('test/subfolder')
        open('test/test.txt', 'w').write('test file\n')
        open('test/subfolder/test2.txt', 'w').write('test file2\n')
        # Upload
        self.ds_object.move_from_storage_service('test/', '/ts/test/')
        # Unsure how to verify. Will raise exception if fails?
        # Cleanup
        os.remove('test/test.txt')
        os.remove('test/subfolder/test2.txt')
        os.removedirs('test/subfolder')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/ts/test/test.txt', auth=auth)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/ts/test/subfolder/test2.txt', auth=auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss.yaml')
    def test_move_to_ss(self):
        # Test file
        self.ds_object.move_to_storage_service('/ts/test.txt', 'folder/test.txt', None)
        assert os.path.isdir('folder')
        assert os.path.isfile('folder/test.txt')
        assert open('folder/test.txt', 'r').read() == 'test file\n'
        # Cleanup
        os.remove('folder/test.txt')
        os.removedirs('folder')
        # Test folder
        self.ds_object.move_to_storage_service('/ts/test/', 'folder/test/', None)
        assert os.path.isdir('folder')
        assert os.path.isdir('folder/test')
        assert os.path.isdir('folder/test/subfolder')
        assert os.path.isfile('folder/test/test.txt')
        assert os.path.isfile('folder/test/subfolder/test2.txt')
        assert open('folder/test/test.txt').read() == 'test file\n'
        assert open('folder/test/subfolder/test2.txt').read() == 'test file2\n'
        # Cleanup
        os.remove('folder/test/test.txt')
        os.remove('folder/test/subfolder/test2.txt')
        os.removedirs('folder/test/subfolder')
