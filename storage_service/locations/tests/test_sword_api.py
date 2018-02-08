import os 

from django.test import TestCase

from locations.api.sword.views import _parse_name_and_content_urls_from_mets_file

import test_locs 
FIXTURES_DIR = test_locs.FIXTURES_READ_DIR

class TestSwordAPI(TestCase):

    def test_removes_forward_slash_parse_fedora_mets(self):
        """ It should remove forward slashes in the deposit name and all
        filenames extracted from a Fedora METS file.
        """
        fedora_mets_path = os.path.join(FIXTURES_DIR, 'fedora_mets_slash.xml')
        mets_parse = _parse_name_and_content_urls_from_mets_file(
            fedora_mets_path)
        fileobjs = mets_parse['objects']
        assert '/' not in mets_parse['deposit_name']
        assert len(fileobjs) > 0
        for fileobj in fileobjs:
            assert '/' not in fileobj['filename']
