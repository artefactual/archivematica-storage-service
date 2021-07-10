import os
import tempfile

from django.test import TestCase

from . import TempDirMixin
from locations import models


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestOfflineReplicaStaging(TempDirMixin, TestCase):

    fixtures = ["base.json", "replica_staging.json"]

    def setUp(self):
        super().setUp()
        self.replica = models.Package.objects.get(id=1)
        self.replica.current_location.space.staging_path = str(self.tmpdir)
        self.replica.current_location.space.save()

        space = models.Space.objects.get(id=1)
        space.path = str(self.tmpdir)
        space.save()

        location = models.Location.objects.get(id=5)
        ss_internal_dir = tempfile.mkdtemp(dir=str(self.tmpdir), prefix="int")
        ss_int_relpath = os.path.relpath(ss_internal_dir, str(self.tmpdir))
        location.relative_path = ss_int_relpath
        location.save()

    def test_delete(self):
        """Test that package in Space isn't deleted."""
        success, err = self.replica.delete_from_storage()
        assert success is False
        assert isinstance(err, NotImplementedError)

    def test_check_fixity(self):
        """Test that fixity check raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.check_fixity()

    def test_browse(self):
        """Test that browse raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.current_location.space.browse("/test/path")

    def test_move_to_storage_service(self):
        """Test that move_to_storage_service raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.current_location.space.move_to_storage_service(
                "/test/path", "/dev/null", self.replica.current_location.space
            )
