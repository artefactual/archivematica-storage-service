import os

from django.test import TestCase
import gnupg

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))

class TestGPG(TestCase):

    fixtures = ['gpg.json']

    def setUp(self):
        self.gpg_object = models.GPG.objects.all()[0]

    def test_move_to_ss_file(self):
        secret_msg = 'testing GPG encryption'
        with open('gpgtest.txt', 'w') as fileo:
            fileo.write(secret_msg)
        self.gpg_object.move_to_storage_service(
            'gpgtest.txt', 'move_to_ss_file_dir/gpgtest.txt', None)
        assert os.path.isdir('move_to_ss_file_dir')
        print os.listdir('move_to_ss_file_dir')
        assert os.path.isfile('move_to_ss_file_dir/gpgtest.txt')
        assert os.path.isfile('move_to_ss_file_dir/gpgtest.txt.gpg')
        with open('move_to_ss_file_dir/gpgtest.txt.gpg', 'rb') as filei:
            gpg_bin = filei.read()
        with open('move_to_ss_file_dir/gpgtest.txt', 'rb') as filei:
            txt_bin = filei.read()
        assert gpg_bin != txt_bin
        gpg = gnupg.GPG()
        with open('move_to_ss_file_dir/gpgtest.txt.gpg', 'rb') as stream:
            decrypted_data = gpg.decrypt_file(stream)
            assert str(decrypted_data) == secret_msg
            assert str(decrypted_data) == txt_bin.decode('utf8')
        # Cleanup
        os.remove('gpgtest.txt')
        os.remove('move_to_ss_file_dir/gpgtest.txt')
        os.remove('move_to_ss_file_dir/gpgtest.txt.gpg')
        os.removedirs('move_to_ss_file_dir')
