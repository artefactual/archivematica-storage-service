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

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_browse.yaml')
    def test_browse(self):
        resp = self.ds_object.browse('SampleTransfers')
        assert resp
        assert resp['directories'] == ['Images', 'Multimedia', 'OCRImage']
        assert resp['entries'] == ['BagTransfer.zip', 'Images', 'Multimedia', 'OCRImage']
        resp = self.ds_object.browse('SampleTransfers/Images')
        assert resp
        assert resp['directories'] == ['pictures']
        assert resp['entries'] == ['799px-Euroleague-LE Roma vs Toulouse IC-27.bmp', 'BBhelmet.ai', 'G31DS.TIF', 'lion.svg', 'Nemastylis_geminiflora_Flower.PNG', 'oakland03.jp2', 'pictures', 'Vector.NET-Free-Vector-Art-Pack-28-Freedom-Flight.eps', 'WFPC01.GIF']

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_file.yaml')
    def test_delete_file(self):
        # Delete file
        self.ds_object.delete_path('delete/delete.zip')
        # Verify deleted
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/delete/delete.zip', auth=auth)
        assert response.status_code == 404

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_folder.yaml')
    def test_delete_folder(self):
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        # Delete folder
        # BUG If delete_path is a folder but provided without a trailing /, will deleted a file with the same name.
        self.ds_object.delete_path('SampleTransfers/delete/')
        # Verify deleted
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/SampleTransfers/delete/delete.svg', auth=auth)
        assert response.status_code == 404
        # Verify that file with same prefix not deleted
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/SampleTransfers/delete.svg', auth=auth)
        assert response.status_code == 200

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_file.yaml')
    def test_move_from_ss_file(self):
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        # Create test.txt
        open('test.txt', 'w').write('test file\n')
        # Upload
        self.ds_object.move_from_storage_service('test.txt', 'test/test.txt')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/test.txt', auth=auth)
        assert response.status_code == 200
        assert response.text == 'test file\n'
        # Cleanup
        os.remove('test.txt')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/test.txt', auth=auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_folder.yaml')
    def test_move_from_ss_folder(self):
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        # Create test folder
        os.mkdir('test')
        os.mkdir('test/subfolder')
        open('test/test.txt', 'w').write('test file\n')
        open('test/subfolder/test2.txt', 'w').write('test file2\n')
        # Upload
        self.ds_object.move_from_storage_service('test/', 'test/foo/')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/foo/test.txt', auth=auth)
        assert response.status_code == 200
        assert response.text == 'test file\n'
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/foo/subfolder/test2.txt', auth=auth)
        assert response.status_code == 200
        assert response.text == 'test file2\n'
        # Cleanup
        os.remove('test/test.txt')
        os.remove('test/subfolder/test2.txt')
        os.removedirs('test/subfolder')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/foo/test.txt', auth=auth)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/foo/subfolder/test2.txt', auth=auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_file.yaml')
    def test_move_to_ss_file(self):
        # Test file
        self.ds_object.move_to_storage_service('test/test.txt', 'folder/test.txt', None)
        assert os.path.isdir('folder')
        assert os.path.isfile('folder/test.txt')
        assert open('folder/test.txt', 'r').read() == 'test file\n'
        # Cleanup
        os.remove('folder/test.txt')
        os.removedirs('folder')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_folder.yaml')
    def test_move_to_ss_folder(self):
        # Test folder
        self.ds_object.move_to_storage_service('test/foo/', 'folder/test/', None)
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

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_folder_globbing.yaml')
    def test_move_to_ss_folder_globbing(self):
        # Test with globbing
        self.ds_object.move_to_storage_service('test/foo/.', 'folder/test/', None)
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

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_percent_encoding.yaml')
    def test_move_to_ss_percent_encoding(self):
        # Move to SS with # in path & filename
        self.ds_object.move_to_storage_service('test/bad #name/bad #name.txt', 'folder/bad #name.txt', None)
        # Verify
        assert os.path.isdir('folder')
        assert os.path.isfile('folder/bad #name.txt')
        assert open('folder/bad #name.txt').read() == 'test file\n'
        # Cleanup
        os.remove('folder/bad #name.txt')
        os.removedirs('folder')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_percent_encoding.yaml')
    def test_move_from_ss_percent_encoding(self):
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        # Create bad #name.txt
        open('bad #name.txt', 'w').write('bad #name file\n')
        # Upload
        self.ds_object.move_from_storage_service('bad #name.txt', 'test/bad #name.txt')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/bad%20%23name.txt', auth=auth)
        assert response.status_code == 200
        assert response.text == 'bad #name file\n'
        # Cleanup
        os.remove('bad #name.txt')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/bad%20%23name.txt', auth=auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_percent_encoding.yaml')
    def test_delete_percent_encoding(self):
        auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.txt', auth=auth)
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path('delete/delete #.txt')
        # Verify deleted
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.txt', auth=auth)
        assert response.status_code == 404
