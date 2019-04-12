import os

import boto3
from django.test import TestCase

from locations import models


class TestS3Storage(TestCase):

    fixtures = ["base.json", "s3.json"]

    def setUp(self):
        self.s3_object = models.S3.objects.get(id=1)

    def test_bucket_name(self):
        assert self.s3_object.bucket_name == "test-bucket"

    def test_bucket_name_falls_back_to_space_id(self):
        self.s3_object.bucket = ""
        self.s3_object.save()

        assert self.s3_object.bucket_name == "ae37f081-8baf-4d5d-9b1f-aebe367f1707"
