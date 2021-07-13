"""Tests for the DSpace REST space."""

from collections import namedtuple
import json
import os
import subprocess
from uuid import uuid4

from lxml import etree
import pytest
import requests

import agentarchives
from agentarchives import archivesspace
from agentarchives.archivesspace.client import CommunicationError
from locations.models import dspace_rest, DSpaceREST, Package, Space


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))

METS_1_PATH = os.path.join(FIXTURES_DIR, "dspacerestmetsmetadata.xml")
METS_1_DSPACE_AIP_COLLECTION = "09c098c1-99b1-4130-8337-7733409d39b8"
METS_1_DSPACE_DIP_COLLECTION = "09c098c1-99b1-4130-8337-7733409d39b8"
METS_1_DC_AUTHOR = "Joel Broham"
METS_1_DC_IDENTIFIER = "0bfc2e03-a3f5-4c06-966f-586187f08cfb"
METS_1_DC_TITLE = "Smalley Smalls"
METS_1_EXTRACTABLE_METADATA = [
    {"language": "", "value": METS_1_DC_AUTHOR, "key": "dcterms.author"},
    {"language": "", "value": METS_1_DC_IDENTIFIER, "key": "dcterms.identifier"},
    {"language": "", "value": METS_1_DC_TITLE, "key": "dc.title"},
]
METS_2_PATH = os.path.join(FIXTURES_DIR, "dspacerestmetsnometadata.xml")

DFLT_DSPACE_AIP_COLLECTION = "aaaaaaaa-99b1-4130-8337-7733409d39b8"
DFLT_DSPACE_DIP_COLLECTION = DFLT_DSPACE_AIP_COLLECTION

DS_URL = "https://test.digitalpreservation.is.ed.ac.uk:443"
DS_HANDLE_URL = f"{DS_URL}/handle"
DS_REST_URL = f"{DS_URL}/rest"
DS_REST_LOGIN_URL = f"{DS_REST_URL}/login"
DS_REST_LOGOUT_URL = f"{DS_REST_URL}/logout"
DS_REST_ITEM_CREATE_URL_TMPLT = f"{DS_REST_URL}/collections/" + "{}/items"
DS_EMAIL = "fakeemail@example.com"
DS_PASSWORD = "abc123!!!"

AS_URL_NO_PORT = "http://aspace2.test.archivematica.org"
AS_PORT = 8089
AS_URL = f"{AS_URL_NO_PORT}:{AS_PORT}"
AS_USER = "someuser"
AS_PASSWORD = "xyz321???"
AS_REPOSITORY = "3"

PACKAGE_UUID = str(uuid4())
DS_ITEM_UUID = str(uuid4())
DS_ITEM_HANDLE = "monkeypants"
DS_ITEM_HANDLE_URL = f"{DS_HANDLE_URL}/{DS_ITEM_HANDLE}"

VERIFY_SSL = False
UPLOAD_TO_TSM = True
AS_ARCHIVAL_OBJECT = "425"
COOKIE = "74364D1D0214772B31D8EA7174F2945A"
HEADER_SET_COOKIE_DFLT = f"JSESSIONID={COOKIE};path=/rest;Secure;HttpOnly"
COOKIES = {"JSESSIONID": COOKIE}
DS_POST_JSON_RESP_DFLT = {"uuid": DS_ITEM_UUID, "handle": DS_ITEM_HANDLE}
JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
SOURCE_PATH = "/a/b/c/"
AIP_NAME_ORIG = "myaip"
AIP_NAME = f"{AIP_NAME_ORIG}-{PACKAGE_UUID}"
AIP_FILENAME = f"{AIP_NAME}.7z"
AIP_SOURCE_PATH = f"{SOURCE_PATH}{AIP_NAME}.7z"
AIP_SOURCE_PATH_DIR = os.path.dirname(AIP_SOURCE_PATH) + "/"
AIP_METS_FILENAME = f"METS.{PACKAGE_UUID}.xml"
AIP_EXTRACTED_METS_RELATIVE_PATH = os.path.join(AIP_NAME, "data", AIP_METS_FILENAME)
AIP_EXTRACTED_METS_PATH = os.path.join(
    AIP_SOURCE_PATH_DIR, AIP_EXTRACTED_METS_RELATIVE_PATH
)

DIP_NAME_ORIG = "mydip"
DIP_NAME = f"{DIP_NAME_ORIG}-{PACKAGE_UUID}"
DIP_SOURCE_PATH = f"{SOURCE_PATH}{DIP_NAME}"
DIP_METS_PATH = os.path.join(DIP_SOURCE_PATH, AIP_METS_FILENAME)

AIP_DEST_PATH = f"/x/y/z/{AIP_NAME}.7z"
DS_REST_AIP_DEPO_URL = "{}/items/{}/bitstreams?name={}".format(
    DS_REST_URL, DS_ITEM_UUID, AIP_FILENAME
)
DS_REST_DIP_DEPO_URL = "{}/items/{}/bitstreams?name={}".format(
    DS_REST_URL, DS_ITEM_UUID, AIP_METS_FILENAME
)
DSPACE_SPACE_EXTRACTABLE_METADATA = [
    {"language": "", "value": AIP_NAME_ORIG.title(), "key": "dc.title"}
]


DSRequestValidity = namedtuple(
    "DSRequestValidity", "is_valid url_substr raise_for_status exc"
)

ds_valid = DSRequestValidity(
    is_valid=True, url_substr=None, raise_for_status=None, exc=None
)

login_failure = DSRequestValidity(
    is_valid=False, url_substr="login", raise_for_status=True, exc=requests.HTTPError()
)

login_exception = DSRequestValidity(
    is_valid=False, url_substr="login", raise_for_status=False, exc=Exception()
)

record_create_failure = DSRequestValidity(
    is_valid=False,
    url_substr="collections",
    raise_for_status=True,
    exc=requests.RequestException(),
)

bitstream_create_failure = DSRequestValidity(
    is_valid=False,
    url_substr="bitstreams",
    raise_for_status=True,
    exc=requests.RequestException(),
)

ASRequestValidity = namedtuple("ASRequestValidity", "is_valid method_that_raises exc")

as_valid = ASRequestValidity(is_valid=True, method_that_raises=None, exc=None)

as_constructor_exc = ASRequestValidity(
    is_valid=False, method_that_raises="constructor", exc=Exception("Could not login")
)

as_ado_exc = ASRequestValidity(
    is_valid=False,
    method_that_raises="add_digital_object",
    exc=CommunicationError(404, None),
)


class MoveFromCaseAIP:
    """Describes a situation where an AIP is being moved from the storage
    service. Note: ``__iter__`` and ``__len__`` make it behave like a
    tuple/list so that pytest.mark.parametrize can handle it.
    """

    attrs = (
        ("package", lambda: MockPackage()),
        ("ds_aip_collection", METS_1_DSPACE_AIP_COLLECTION),
        ("metadata", METS_1_EXTRACTABLE_METADATA),
        ("package_source_path", AIP_SOURCE_PATH),
        ("package_mets_path", AIP_EXTRACTED_METS_PATH),
        ("ds_request_validity", ds_valid),
        ("as_credentials_set", False),
        ("as_credentials_valid", as_valid),
        ("upload_to_tsm", UPLOAD_TO_TSM),
    )

    def __init__(self, **kwargs):
        for key, dflt in self.attrs:
            val = kwargs.get(key, dflt)
            if callable(val):
                val = val()
            setattr(self, key, val)

    def __len__(self):
        return len(self.attrs)

    def __iter__(self):
        for key, _ in self.attrs:
            yield getattr(self, key)


class MoveFromCaseDIP(MoveFromCaseAIP):
    """Describes a situation where a DIP is being moved from the storage
    service.
    """

    attrs = (
        ("package", lambda: MockPackage(package_type=Package.DIP)),
        ("ds_aip_collection", METS_1_DSPACE_DIP_COLLECTION),
        ("metadata", METS_1_EXTRACTABLE_METADATA),
        ("package_source_path", DIP_SOURCE_PATH),
        ("package_mets_path", DIP_METS_PATH),
        ("ds_request_validity", ds_valid),
        ("as_credentials_set", False),
        ("as_credentials_valid", as_valid),
        ("upload_to_tsm", UPLOAD_TO_TSM),
    )


class MockPackage:
    """Class to mock models.Package."""

    def __init__(self, **kwargs):
        self.uuid = kwargs.get("uuid", PACKAGE_UUID)
        self.package_type = kwargs.get("package_type", Package.AIP)
        self.isfile = kwargs.get("isfile", True)
        self.fake_mets_file = kwargs.get("fake_mets_file", open(METS_1_PATH))


class MockProcess:
    """Class to mock the output of ``subprocess.Popen``."""

    def __init__(self, command, **kwargs):
        self.command = command
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.stdout = "Output of a subprocess call"
        self.stderr = ""

    def communicate(self):
        return self.stdout, self.stderr


class FakeDSpaceRESTPOSTResponse:
    """Mock class that emulates all of the possible responses to POST requests
    to the DSpace REST API that are issuable by the DSpaceREST space.
    """

    def __init__(self, **kwargs):
        self.header_set_cookie = kwargs.get("header_set_cookie", HEADER_SET_COOKIE_DFLT)
        self.status_code = None
        self._json = kwargs.get("json", DS_POST_JSON_RESP_DFLT)
        self._raise = kwargs.get("_raise")

    @property
    def headers(self):
        return {"Set-Cookie": self.header_set_cookie}

    def json(self):
        return self._json

    def raise_for_status(self):

        if self._raise:
            self.status_code = 401
            raise self._raise


class FakeArchivesSpaceClient:
    """Minimal mocks of agentarchives.archivesspace.ArchivesSpaceClient."""

    def __init__(self, exc=None):
        self.exc = exc
        self.args = None
        self.kwargs = None

    def add_digital_object(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        if self.exc:
            raise self.exc


@pytest.mark.parametrize(
    (
        "package",
        "ds_aip_collection",
        "metadata",
        "package_source_path",
        "package_mets_path",
        "ds_request_validity",
        "as_credentials_set",
        "as_credentials_valid",
        "upload_to_tsm",
    ),
    [
        # Null package should cause early return
        MoveFromCaseAIP(package=None),
        # Uncompressed AIP should raise an exception
        MoveFromCaseAIP(package=MockPackage(isfile=False)),
        # Compressed AIP with DSpace metadata in the METS should work
        MoveFromCaseAIP(),
        # Compressed AIP with TSM upload disabled
        MoveFromCaseAIP(upload_to_tsm=False),
        # Compressed AIP with NO DSpace metadata in the METS should work and
        # use metadata from DSpaceREST model attributes
        MoveFromCaseAIP(
            package=MockPackage(fake_mets_file=open(METS_2_PATH)),
            ds_aip_collection=DFLT_DSPACE_AIP_COLLECTION,
            metadata=DSPACE_SPACE_EXTRACTABLE_METADATA,
        ),
        # Simulate DSpace login request returning a bad exit code
        MoveFromCaseAIP(ds_request_validity=login_failure),
        # Simulate generic DSpace login request failure
        MoveFromCaseAIP(ds_request_validity=login_exception),
        # Simulate DSpace record create request failure
        MoveFromCaseAIP(ds_request_validity=record_create_failure),
        # Simulate DSpace bitstream deposit request failure
        MoveFromCaseAIP(ds_request_validity=bitstream_create_failure),
        # DIP with DSpace metadata in the METS should work and use metadata
        # from DSpaceREST model attributes
        MoveFromCaseDIP(),
        # Same as above but with ArchivesSpace credentials set on the space so
        # AS calls should be made.
        MoveFromCaseDIP(as_credentials_set=True),
        # Simulate ``client = archivesspace.ArchivesSpaceClient(...) raising an
        # exception.
        MoveFromCaseDIP(
            as_credentials_set=True, as_credentials_valid=as_constructor_exc
        ),
        # Simulate ``client.add_digital_object(...) raising
        # ``CommunicationError``.
        MoveFromCaseDIP(as_credentials_set=True, as_credentials_valid=as_ado_exc),
    ],
)
def test_move_from_storage_service(
    mocker,
    package,
    ds_aip_collection,
    metadata,
    package_source_path,
    package_mets_path,
    ds_request_validity,
    as_credentials_set,
    as_credentials_valid,
    upload_to_tsm,
):
    mocker.patch("os.path.isfile", return_value=getattr(package, "isfile", True))
    dspace_rest_space = DSpaceREST(
        space=Space(),
        ds_rest_url=DS_REST_URL,
        ds_user=DS_EMAIL,
        ds_password=DS_PASSWORD,
        ds_dip_collection=DFLT_DSPACE_DIP_COLLECTION,
        ds_aip_collection=DFLT_DSPACE_AIP_COLLECTION,
        as_archival_object=AS_ARCHIVAL_OBJECT,
        verify_ssl=VERIFY_SSL,
        upload_to_tsm=upload_to_tsm,
    )
    if as_credentials_set:
        dspace_rest_space.as_url = AS_URL
        dspace_rest_space.as_user = AS_USER
        dspace_rest_space.as_password = AS_PASSWORD
        dspace_rest_space.as_repository = AS_REPOSITORY

    if not package:
        with pytest.raises(dspace_rest.DSpaceRESTException) as excinfo:
            dspace_rest_space.move_from_storage_service(
                package_source_path, AIP_DEST_PATH, package=package
            )
        assert str(excinfo.value) == ("DSpace requires package param.")
        return

    if package.package_type == Package.AIP and not package.isfile:
        with pytest.raises(dspace_rest.DSpaceRESTException) as excinfo:
            dspace_rest_space.move_from_storage_service(
                package_source_path, AIP_DEST_PATH, package=package
            )
        assert str(excinfo.value) == (
            "Storing in DSpace does not support uncompressed AIPs."
        )
        return

    # Simple patches
    mocker.patch("subprocess.Popen", return_value=MockProcess(["fake-command"]))
    mocker.patch("lxml.etree.parse", return_value=etree.parse(package.fake_mets_file))
    mocker.patch("os.remove")
    mocker.patch("builtins.open")
    mocker.patch("os.listdir", return_value=[AIP_METS_FILENAME])
    mocker.patch("os.walk", return_value=[("", [], [AIP_METS_FILENAME])])

    # Patch ``requests.post``
    def mock_requests_post(*args, **kwargs):
        if (not ds_request_validity.is_valid) and (
            ds_request_validity.url_substr in args[0]
        ):
            if ds_request_validity.raise_for_status:
                return FakeDSpaceRESTPOSTResponse(_raise=ds_request_validity.exc)
            raise ds_request_validity.exc
        return FakeDSpaceRESTPOSTResponse()

    mocker.patch("requests.post", side_effect=mock_requests_post)

    # Patch ``agentarchives.archivesspace.ArchivesSpaceClient``
    if (
        not as_credentials_valid.is_valid
    ) and as_credentials_valid.method_that_raises == "add_digital_object":
        fake_as_client = FakeArchivesSpaceClient(exc=as_credentials_valid.exc)
    else:
        fake_as_client = FakeArchivesSpaceClient()
    mocker.patch(
        "agentarchives.archivesspace.ArchivesSpaceClient", return_value=fake_as_client
    )
    if not as_credentials_valid.is_valid:
        agentarchives.archivesspace.ArchivesSpaceClient.side_effect = (
            as_credentials_valid.exc
        )

    # Simulate AS request-related failure
    if not as_credentials_valid.is_valid:
        with pytest.raises(dspace_rest.DSpaceRESTException) as excinfo:
            dspace_rest_space.move_from_storage_service(
                package_source_path, AIP_DEST_PATH, package=package
            )
        return

    # Simulate AS "add digital object" failure
    if (
        not as_credentials_valid.is_valid
    ) and as_credentials_valid.method_that_raises == "constructor":
        with pytest.raises(dspace_rest.DSpaceRESTException) as excinfo:
            dspace_rest_space.move_from_storage_service(
                package_source_path, AIP_DEST_PATH, package=package
            )
        assert excinfo.value.message == (
            "Error depositing to DSpace or ArchiveSpace: Could not login to"
            " ArchivesSpace server: {}, port: {}, user: {}, repository:"
            " {}".format(AS_URL_NO_PORT, AS_PORT, AS_USER, AS_REPOSITORY)
        )
        return

    if not ds_request_validity.is_valid:
        with pytest.raises(dspace_rest.DSpaceRESTException) as excinfo:
            dspace_rest_space.move_from_storage_service(
                package_source_path, AIP_DEST_PATH, package=package
            )
        return

    # Call the test-targeting method in the happy path
    dspace_rest_space.move_from_storage_service(
        package_source_path, AIP_DEST_PATH, package=package
    )

    # Assertions about the 4 requests.post calls:
    # 1. login to DSpace,
    # 2. create a DSpace item
    # 3. deposit a file to DSpace (.7z file for AIP; METS.xml file for DIP,
    #    which is contrived, but makes the testing easier.)
    # 4. logout from DSpace.
    (
        actual_login_call,
        (_, actual_create_item_args, actual_create_item_kwargs),
        (_, actual_bitstream_args, actual_bitstream_kwargs),
        actual_logout_call,
    ) = requests.post.mock_calls
    assert actual_login_call == mocker.call(
        DS_REST_LOGIN_URL,
        cookies=None,
        data={"password": DS_PASSWORD, "email": DS_EMAIL},
        headers=None,
        verify=VERIFY_SSL,
    )
    assert actual_logout_call == mocker.call(
        DS_REST_LOGOUT_URL,
        cookies=COOKIES,
        data=None,
        headers=JSON_HEADERS,
        verify=VERIFY_SSL,
    )
    assert actual_create_item_args == (
        DS_REST_ITEM_CREATE_URL_TMPLT.format(ds_aip_collection),
    )
    assert actual_create_item_kwargs["verify"] == VERIFY_SSL
    assert actual_create_item_kwargs["cookies"] == COOKIES
    assert json.loads(actual_create_item_kwargs["data"]) == {
        "type": "item",
        "metadata": metadata,
    }
    assert actual_create_item_kwargs["headers"] == JSON_HEADERS
    assert actual_bitstream_kwargs["verify"] == VERIFY_SSL
    assert actual_bitstream_kwargs["cookies"] == COOKIES
    assert actual_bitstream_kwargs["headers"] == JSON_HEADERS
    etree.parse.assert_called_once_with(package_mets_path)

    if package.package_type == Package.DIP:
        # No METS extraction happens with DIP, therefore no removal needed
        os.remove.assert_not_called()
        os.listdir.assert_called_with(package_source_path)
        assert actual_bitstream_args == (DS_REST_DIP_DEPO_URL,)
        if as_credentials_set:
            archivesspace.ArchivesSpaceClient.assert_called_once_with(
                AS_URL_NO_PORT, AS_USER, AS_PASSWORD, AS_PORT, AS_REPOSITORY
            )
            assert fake_as_client.args == (
                "/repositories/{}/archival_objects/{}".format(
                    AS_REPOSITORY, AS_ARCHIVAL_OBJECT
                ),
                PACKAGE_UUID,
            )
            assert fake_as_client.kwargs == {
                "uri": DS_ITEM_HANDLE_URL,
                "title": METS_1_DC_TITLE,
            }
        else:
            archivesspace.ArchivesSpaceClient.assert_not_called()
        return

    os.remove.assert_called_once_with(package_mets_path)
    os.listdir.assert_not_called()
    archivesspace.ArchivesSpaceClient.assert_not_called()
    assert actual_bitstream_args == (DS_REST_AIP_DEPO_URL,)

    # Assertions about the subprocess.Popen call(s)
    expected_unar_args = (
        [
            "unar",
            "-force-overwrite",
            "-o",
            AIP_SOURCE_PATH_DIR,
            package_source_path,
            AIP_EXTRACTED_METS_RELATIVE_PATH,
        ],
    )
    if upload_to_tsm:
        # 1. to unar to extract the AIP METS
        # 2. to dsmc (Tivoli Storage Manager)
        (
            (_, actual_unar_args, _),
            (_, actual_dsmc_args, _),
        ) = subprocess.Popen.mock_calls
        assert actual_unar_args == expected_unar_args
        assert actual_dsmc_args == (["dsmc", "archive", package_source_path],)
    else:
        # Assertions about the 1 subprocess.Popen call:
        # 1. to unar to extract the AIP METS
        ((_, actual_unar_args, _),) = subprocess.Popen.mock_calls
        assert actual_unar_args == expected_unar_args
