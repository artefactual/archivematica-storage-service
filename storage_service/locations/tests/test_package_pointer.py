import os
from uuid import uuid4

import metsrw
from metsrw.plugins import premisrw
from django.test import TestCase

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))


TEST_PREMIS_OBJECT_UUID = str(uuid4())
TEST_PREMIS_OBJECT_MESSAGE_DIGEST_ALGORITHM = "sha256"
TEST_PREMIS_OBJECT_MESSAGE_DIGEST = (
    "78e4509313928d2964fe877a6a82f1ba728c171eedf696e3f5b0aed61ec547f6"
)
TEST_PREMIS_OBJECT_SIZE = "11854"
TEST_PREMIS_OBJECT_FORMAT_NAME = "7Zip format"
TEST_PREMIS_OBJECT_FORMAT_REGISTRY_KEY = "fmt/484"
TEST_PREMIS_OBJECT_DATE_CREATED_BY_APPLICATION = "2017-08-15T00:30:55"
TEST_PREMIS_OBJECT_CREATING_APPLICATION_NAME = "7-Zip"
TEST_PREMIS_OBJECT_CREATING_APPLICATION_VERSION = (
    "p7zip Version 9.20 (locale=en_US.UTF-8,Utf16=on,HugeFiles=on,2 CPUs)"
)
TEST_PREMIS_OBJECT_AIP_SUBTYPE = "Some strange subtype"
TEST_PREMIS_OBJECT_ATTRS = premisrw.PREMIS_META.copy()
TEST_PREMIS_OBJECT_ATTRS["xsi:type"] = "premis:file"
TEST_PREMIS_OBJECT = (
    "object",
    TEST_PREMIS_OBJECT_ATTRS,
    (
        "object_identifier",
        ("object_identifier_type", "UUID"),
        ("object_identifier_value", TEST_PREMIS_OBJECT_UUID),
    ),
    (
        "object_characteristics",
        ("composition_level", "1"),
        (
            "fixity",
            ("message_digest_algorithm", TEST_PREMIS_OBJECT_MESSAGE_DIGEST_ALGORITHM),
            ("message_digest", TEST_PREMIS_OBJECT_MESSAGE_DIGEST),
        ),
        ("size", TEST_PREMIS_OBJECT_SIZE),
        (
            "format",
            (
                "format_designation",
                ("format_name", TEST_PREMIS_OBJECT_FORMAT_NAME),
                ("format_version", ""),
            ),
            (
                "format_registry",
                ("format_registry_name", "PRONOM"),
                ("format_registry_key", TEST_PREMIS_OBJECT_FORMAT_REGISTRY_KEY),
            ),
        ),
        (
            "creating_application",
            ("creating_application_name", TEST_PREMIS_OBJECT_CREATING_APPLICATION_NAME),
            (
                "creating_application_version",
                TEST_PREMIS_OBJECT_CREATING_APPLICATION_VERSION,
            ),
            (
                "date_created_by_application",
                TEST_PREMIS_OBJECT_DATE_CREATED_BY_APPLICATION,
            ),
        ),
    ),
)


TEST_PREMIS_AGENT_1_IDENTIFIER_TYPE = "preservation system"
TEST_PREMIS_AGENT_1_IDENTIFIER_VALUE = "Archivematica-1.6.1"
TEST_PREMIS_AGENT_1_NAME = "Archivematica"
TEST_PREMIS_AGENT_1_TYPE = "software"
TEST_PREMIS_AGENT_1 = (
    "agent",
    premisrw.PREMIS_META,
    (
        "agent_identifier",
        ("agent_identifier_type", TEST_PREMIS_AGENT_1_IDENTIFIER_TYPE),
        ("agent_identifier_value", TEST_PREMIS_AGENT_1_IDENTIFIER_VALUE),
    ),
    ("agent_name", TEST_PREMIS_AGENT_1_NAME),
    ("agent_type", TEST_PREMIS_AGENT_1_TYPE),
)

TEST_PREMIS_AGENT_2_IDENTIFIER_TYPE = "repository code"
TEST_PREMIS_AGENT_2_IDENTIFIER_VALUE = "username"
TEST_PREMIS_AGENT_2_NAME = "username"
TEST_PREMIS_AGENT_2_TYPE = "organization"
TEST_PREMIS_AGENT_2 = (
    "agent",
    premisrw.PREMIS_META,
    (
        "agent_identifier",
        ("agent_identifier_type", TEST_PREMIS_AGENT_2_IDENTIFIER_TYPE),
        ("agent_identifier_value", TEST_PREMIS_AGENT_2_IDENTIFIER_VALUE),
    ),
    ("agent_name", TEST_PREMIS_AGENT_2_NAME),
    ("agent_type", TEST_PREMIS_AGENT_2_TYPE),
)

TEST_PREMIS_EVENT_AGENTS = (
    {
        "identifier_type": TEST_PREMIS_AGENT_1_IDENTIFIER_TYPE,
        "identifier_value": TEST_PREMIS_AGENT_1_IDENTIFIER_VALUE,
    },
    {
        "identifier_type": TEST_PREMIS_AGENT_2_IDENTIFIER_TYPE,
        "identifier_value": TEST_PREMIS_AGENT_2_IDENTIFIER_VALUE,
    },
)

TEST_PREMIS_EVENT_IDENTIFIER_VALUE = str(uuid4())
TEST_PREMIS_EVENT_TYPE = "compression"
TEST_PREMIS_EVENT_DATE_TIME = "2017-08-15T00:30:55"
TEST_PREMIS_EVENT_DETAIL = (
    "program=7z; "
    "version=p7zip Version 9.20 "
    "(locale=en_US.UTF-8,Utf16=on,HugeFiles=on,2 CPUs); "
    "algorithm=bzip2"
)
TEST_PREMIS_EVENT_OUTCOME_DETAIL_NOTE = 'Standard Output="..."; Standard Error=""'

TEST_PREMIS_EVENT = (
    "event",
    premisrw.PREMIS_META,
    (
        "event_identifier",
        ("event_identifier_type", "UUID"),
        ("event_identifier_value", TEST_PREMIS_EVENT_IDENTIFIER_VALUE),
    ),
    ("event_type", TEST_PREMIS_EVENT_TYPE),
    ("event_date_time", TEST_PREMIS_EVENT_DATE_TIME),
    ("event_detail", TEST_PREMIS_EVENT_DETAIL),
    (
        "event_outcome_information",
        ("event_outcome",),
        (
            "event_outcome_detail",
            ("event_outcome_detail_note", TEST_PREMIS_EVENT_OUTCOME_DETAIL_NOTE),
        ),
    ),
    (
        "linking_agent_identifier",
        ("linking_agent_identifier_type", TEST_PREMIS_AGENT_1_IDENTIFIER_TYPE),
        ("linking_agent_identifier_value", TEST_PREMIS_AGENT_1_IDENTIFIER_VALUE),
    ),
    (
        "linking_agent_identifier",
        ("linking_agent_identifier_type", TEST_PREMIS_AGENT_2_IDENTIFIER_TYPE),
        ("linking_agent_identifier_value", TEST_PREMIS_AGENT_2_IDENTIFIER_VALUE),
    ),
)


class TestPackagePointer(TestCase):
    """Test the package model's pointer file-related capabilities."""

    fixtures = ["base.json", "package.json"]

    def setUp(self):
        self.package = models.Package.objects.all()[0]

    def test_create_pointer_file(self):
        """ It should be able to create a pointer file. """
        pointer_file = self.package.create_pointer_file(
            TEST_PREMIS_OBJECT,
            [TEST_PREMIS_EVENT],
            premis_agents=[TEST_PREMIS_AGENT_1, TEST_PREMIS_AGENT_2],
            validate=False,
        )
        is_valid, report = metsrw.validate(
            pointer_file.serialize(), schematron=metsrw.AM_PNTR_SCT_PATH
        )
        assert is_valid
