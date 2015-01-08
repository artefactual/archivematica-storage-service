import os
import requests

from django.test import TestCase
import vcr

from locations import models


class TestDuracloud(TestCase):

    fixtures = ['base.json', 'duracloud.json']

    def setUp(self):
        self.ds_object = models.Duracloud.objects.all()[0]
        self.auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)

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
        assert resp['properties']['Images']['object count'] == 10
        assert resp['properties']['Multimedia']['object count'] == 7
        assert resp['properties']['OCRImage']['object count'] == 1
        resp = self.ds_object.browse('SampleTransfers/Images')
        assert resp
        assert resp['directories'] == ['pictures']
        assert resp['entries'] == ['799px-Euroleague-LE Roma vs Toulouse IC-27.bmp', 'BBhelmet.ai', 'G31DS.TIF', 'lion.svg', 'Nemastylis_geminiflora_Flower.PNG', 'oakland03.jp2', 'pictures', 'Vector.NET-Free-Vector-Art-Pack-28-Freedom-Flight.eps', 'WFPC01.GIF']
        assert resp['properties']['pictures']['object count'] == 2

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_browse_split_files.yaml')
    def test_browse_split_files(self):
        # Hide split files
        resp = self.ds_object.browse('chunked')
        assert resp
        assert resp['directories'] == []
        assert resp['entries'] == ['chunked_image.jpg']

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_file.yaml')
    def test_delete_file(self):
        # Verify exists
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path('delete/delete.svg')
        # Verify deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 404

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_folder.yaml')
    def test_delete_folder(self):
        # Verify exists
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete/delete.svg', auth=self.auth)
        assert response.status_code == 200
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 200
        # Delete folder
        # BUG If delete_path is a folder but provided without a trailing /, will deleted a file with the same name.
        self.ds_object.delete_path('delete/delete/')
        # Verify deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete/delete.svg', auth=self.auth)
        assert response.status_code == 404
        # Verify that file with same prefix not deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 200

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_percent_encoding.yaml')
    def test_delete_percent_encoding(self):
        # Verify exists
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.svg', auth=self.auth)
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path('delete/delete #.svg')
        # Verify deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.svg', auth=self.auth)
        assert response.status_code == 404

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_delete_chunked_file.yaml')
    def test_delete_chunked_file(self):
        # Ensure file exists
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 404
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-manifest', auth=self.auth)
        assert response.status_code == 200
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dnd', auth=self.auth)
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path('delete/delete.svg')
        # Verify deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg', auth=self.auth)
        assert response.status_code == 404
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-manifest', auth=self.auth)
        assert response.status_code == 404
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-chunk-0000', auth=self.auth)
        assert response.status_code == 404
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-chunk-0001', auth=self.auth)
        assert response.status_code == 404
        # Verify file with same prefix not deleted
        response = requests.head('https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dnd', auth=self.auth)
        assert response.status_code == 200

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_file.yaml')
    def test_move_from_ss_file(self):
        # Create test.txt
        open('test.txt', 'w').write('test file\n')
        # Upload
        self.ds_object.move_from_storage_service('test.txt', 'test/test.txt')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/test.txt', auth=self.auth)
        assert response.status_code == 200
        assert response.text == 'test file\n'
        # Cleanup
        os.remove('test.txt')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/test.txt', auth=self.auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_folder.yaml')
    def test_move_from_ss_folder(self):
        # Create test folder
        os.mkdir('test')
        os.mkdir('test/subfolder')
        open('test/test.txt', 'w').write('test file\n')
        open('test/subfolder/test2.txt', 'w').write('test file2\n')
        # Upload
        self.ds_object.move_from_storage_service('test/', 'test/foo/')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/foo/test.txt', auth=self.auth)
        assert response.status_code == 200
        assert response.text == 'test file\n'
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/foo/subfolder/test2.txt', auth=self.auth)
        assert response.status_code == 200
        assert response.text == 'test file2\n'
        # Cleanup
        os.remove('test/test.txt')
        os.remove('test/subfolder/test2.txt')
        os.removedirs('test/subfolder')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/foo/test.txt', auth=self.auth)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/foo/subfolder/test2.txt', auth=self.auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_percent_encoding.yaml')
    def test_move_from_ss_percent_encoding(self):
        # Create bad #name.txt
        open('bad #name.txt', 'w').write('bad #name file\n')
        # Upload
        self.ds_object.move_from_storage_service('bad #name.txt', 'test/bad #name.txt')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/test/bad%20%23name.txt', auth=self.auth)
        assert response.status_code == 200
        assert response.text == 'bad #name file\n'
        # Cleanup
        os.remove('bad #name.txt')
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/test/bad%20%23name.txt', auth=self.auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_from_ss_chunked.yaml')
    def test_move_from_ss_chunked_file(self):
        file_path = 'locations/fixtures/chunk_file.jpg'
        self.ds_object.CHUNK_SIZE = 100 * 1024  # Set testing chunk size
        # Upload
        self.ds_object.move_from_storage_service(file_path, 'chunked/chunked #image.jpg')
        # Verify
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.jpg', auth=self.auth)
        assert response.status_code == 404
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.jpg.dura-manifest', auth=self.auth)
        assert response.status_code == 200
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.jpg.dura-chunk-0000', auth=self.auth)
        assert response.status_code == 200
        response = requests.get('https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.jpg.dura-chunk-0001', auth=self.auth)
        assert response.status_code == 200
        # Cleanup
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/chunked/chunked%20%23image.jpg.dura-manifest', auth=self.auth)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/chunked/chunked%20%23image.jpg.dura-chunk-0000', auth=self.auth)
        requests.delete('https://' + self.ds_object.host + '/durastore/' + self.ds_object.duraspace + '/chunked/chunked%20%23image.jpg.dura-chunk-0001', auth=self.auth)

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_file.yaml')
    def test_move_to_ss_file(self):
        # Test file
        self.ds_object.move_to_storage_service('test/test.txt', 'move_to_ss_file_dir/test.txt', None)
        assert os.path.isdir('move_to_ss_file_dir')
        assert os.path.isfile('move_to_ss_file_dir/test.txt')
        assert open('move_to_ss_file_dir/test.txt', 'r').read() == 'test file\n'
        # Cleanup
        os.remove('move_to_ss_file_dir/test.txt')
        os.removedirs('move_to_ss_file_dir')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_folder.yaml')
    def test_move_to_ss_folder(self):
        # Test folder
        self.ds_object.move_to_storage_service('test/foo/', 'move_to_ss_folder_dir/test/', None)
        assert os.path.isdir('move_to_ss_folder_dir')
        assert os.path.isdir('move_to_ss_folder_dir/test')
        assert os.path.isdir('move_to_ss_folder_dir/test/subfolder')
        assert os.path.isfile('move_to_ss_folder_dir/test/test.txt')
        assert os.path.isfile('move_to_ss_folder_dir/test/subfolder/test2.txt')
        assert open('move_to_ss_folder_dir/test/test.txt').read() == 'test file\n'
        assert open('move_to_ss_folder_dir/test/subfolder/test2.txt').read() == 'test file2\n'
        # Cleanup
        os.remove('move_to_ss_folder_dir/test/test.txt')
        os.remove('move_to_ss_folder_dir/test/subfolder/test2.txt')
        os.removedirs('move_to_ss_folder_dir/test/subfolder')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_folder_globbing.yaml')
    def test_move_to_ss_folder_globbing(self):
        # Test with globbing
        self.ds_object.move_to_storage_service('test/foo/.', 'move_to_ss_folder_globbing_dir/test/', None)
        assert os.path.isdir('move_to_ss_folder_globbing_dir')
        assert os.path.isdir('move_to_ss_folder_globbing_dir/test')
        assert os.path.isdir('move_to_ss_folder_globbing_dir/test/subfolder')
        assert os.path.isfile('move_to_ss_folder_globbing_dir/test/test.txt')
        assert os.path.isfile('move_to_ss_folder_globbing_dir/test/subfolder/test2.txt')
        assert open('move_to_ss_folder_globbing_dir/test/test.txt').read() == 'test file\n'
        assert open('move_to_ss_folder_globbing_dir/test/subfolder/test2.txt').read() == 'test file2\n'
        # Cleanup
        os.remove('move_to_ss_folder_globbing_dir/test/test.txt')
        os.remove('move_to_ss_folder_globbing_dir/test/subfolder/test2.txt')
        os.removedirs('move_to_ss_folder_globbing_dir/test/subfolder')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_percent_encoding.yaml')
    def test_move_to_ss_percent_encoding(self):
        # Move to SS with # in path & filename
        self.ds_object.move_to_storage_service('test/bad #name/bad #name.txt', 'move_to_ss_percent_dir/bad #name.txt', None)
        # Verify
        assert os.path.isdir('move_to_ss_percent_dir')
        assert os.path.isfile('move_to_ss_percent_dir/bad #name.txt')
        assert open('move_to_ss_percent_dir/bad #name.txt').read() == 'test file\n'
        # Cleanup
        os.remove('move_to_ss_percent_dir/bad #name.txt')
        os.removedirs('move_to_ss_percent_dir')

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/duracloud_move_to_ss_chunked_file.yaml')
    def test_move_to_ss_chunked_file(self):
        # chunked #image.jpg is actually chunked
        self.ds_object.move_to_storage_service('chunked/chunked #image.jpg', 'move_to_ss_chunked/chunked #image.jpg', None)
        # Verify
        assert os.path.isdir('move_to_ss_chunked')
        assert not os.path.exists('move_to_ss_chunked/chunked #image.jpg.dura-manifest')
        assert not os.path.exists('move_to_ss_chunked/chunked #image.jpg.dura-chunk-0000')
        assert not os.path.exists('move_to_ss_chunked/chunked #image.jpg.dura-chunk-0001')
        assert os.path.isfile('move_to_ss_chunked/chunked #image.jpg')
        assert os.path.getsize('move_to_ss_chunked/chunked #image.jpg') == 158131

        # Cleanup
        os.remove('move_to_ss_chunked/chunked #image.jpg')
        os.removedirs('move_to_ss_chunked')
