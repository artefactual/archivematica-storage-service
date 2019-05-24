import os

import boto3
from django.test import TestCase
from moto import mock_s3

from locations import models


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestS3Storage(TestCase):

    fixtures = ["base.json", "s3.json"]

    def setUp(self):
        self.s3_object = models.S3.objects.get(id=1)

    def test_bucket_name(self):
        assert self.s3_object.bucket_name == "test-bucket"

    def test_bucket_name_falls_back_to_space_id(self):
        self.s3_object.bucket = ''
        self.s3_object.save()

        assert self.s3_object.bucket_name == "ae37f081-8baf-4d5d-9b1f-aebe367f1707"

    @mock_s3
    def test_browse(self):
        client = boto3.client("s3", region_name='us-east-1')
        client.create_bucket(Bucket='test-bucket')

        client.upload_file(
            os.path.join(FIXTURES_DIR, 'working_bag.zip'),
           'test-bucket',
           'subdir/bag.zip')

        contents = self.s3_object.browse('/')
        assert 'subdir' in contents['entries']
        assert 'subdir' in contents['directories']

        contents = self.s3_object.browse('/subdir')
        assert 'bag.zip' in contents['entries']
        properties = contents['properties']['bag.zip']
        assert 'timestamp' in properties
        assert properties['e_tag'] == '"e917f867114dedf9bdb430e838da647d"'
        assert properties['size'] == 1564
