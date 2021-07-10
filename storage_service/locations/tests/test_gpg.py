"""Tests for the GPG encrypted space."""

from collections import namedtuple
import os
import tarfile

from django.test import TestCase
from metsrw.plugins import premisrw
import pytest

from common import gpgutils, utils
from locations.models import gpg, Package, space


GPG_VERSION = "1.4.16"
SS_VERSION = "0.11.0"
SUCCESS_STATUS = "good times"
DECRYPT_RET_FAIL_STATUS = "bad stuff happened"
RAW_GPG_VERSION = (1, 4, 16)
SOME_FINGERPRINT = EXP_FINGERPRINT = "B9C518917A958DD0B1F5E1B80C3D34DDA5958532"
SOME_OTHER_FINGERPRINT = "BBBB18917A958DD0B1F5E1B80C3D34DDA595BBBB"
TEST_AGENTS = [
    premisrw.PREMISAgent(
        data=(
            "agent",
            premisrw.PREMIS_META,
            (
                "agent_identifier",
                ("agent_identifier_type", "preservation system"),
                (
                    "agent_identifier_value",
                    f"Archivematica-Storage-Service-{SS_VERSION}",
                ),
            ),
            ("agent_name", "Archivematica Storage Service"),
            ("agent_type", "software"),
        )
    )
]
BROWSE_FAIL_DICT = {"directories": [], "entries": [], "properties": {}}


FakeGPGRet = namedtuple("FakeGPGRet", "ok status stderr")
ExTarCase = namedtuple("ExTarCase", "path isdir raises expected")
CrTarCase = namedtuple("CrTarCase", "path isfile istar raises expected")
DecryptCase = namedtuple(
    "DecryptCase", "path isfile createsdecryptfile decryptret expected"
)
EncryptCase = namedtuple("EncryptCase", "path isdir encrpathisfile encryptret expected")
BrowseCase = namedtuple("BrowseCase", "path encrpath existsafter expect")
MoveFromCase = namedtuple(
    "MoveFromCase", "src_path dst_path package encrypt_ret expect"
)
MoveToCase = namedtuple(
    "MoveToCase", "src_path dst_path src_exists1 src_exists2 encr_path expect"
)


ENCRYPT_RET_SUCCESS = DECRYPT_RET_SUCCESS = FakeGPGRet(
    ok=True, status=SUCCESS_STATUS, stderr=""
)
ENCRYPT_RET_FAIL = DECRYPT_RET_FAIL = FakeGPGRet(
    ok=False, status=DECRYPT_RET_FAIL_STATUS, stderr=""
)


class MockPackage:
    def __init__(self, **kwargs):
        self.encryption_key_fingerprint = kwargs.get("fingerprint", SOME_FINGERPRINT)
        self._should_have_pointer_file = kwargs.get("should_have_pointer", True)
        self.save_called = 0

    def save(self):
        self.save_called += 1

    def should_have_pointer_file(self):
        return self._should_have_pointer_file


@pytest.mark.parametrize(
    "src_path, dst_path, src_exists1, src_exists2, encr_path, expect",
    [
        MoveToCase(
            src_path="/a/b/c",
            dst_path="/x/y/z",
            src_exists1=True,
            src_exists2=True,
            encr_path="/a/b/c",
            expect="success",
        ),
        MoveToCase(
            src_path="/a/b/c/somefile.jpg",
            dst_path="/x/y/z/somefile.jpg",
            src_exists1=False,
            src_exists2=True,
            encr_path="/a/b/c",
            expect="success",
        ),
        MoveToCase(
            src_path="/a/b/c/somefile.jpg",
            dst_path="/x/y/z/somefile.jpg",
            src_exists1=False,
            src_exists2=True,
            encr_path=None,
            expect="fail",
        ),
        MoveToCase(
            src_path="/a/b/c/somefile.jpg",
            dst_path="/x/y/z/somefile.jpg",
            src_exists1=False,
            src_exists2=False,
            encr_path="/a/b/c",
            expect="fail",
        ),
    ],
)
def test_move_to_storage_service(
    mocker, src_path, dst_path, src_exists1, src_exists2, encr_path, expect
):
    gpg_space = gpg.GPG(key=SOME_FINGERPRINT, space=space.Space())
    mocker.patch.object(gpg_space.space, "create_local_directory")
    mocker.patch.object(gpg_space.space, "move_rsync")
    mocker.patch.object(gpg, "_gpg_decrypt")
    mocker.patch.object(gpg, "_gpg_encrypt")
    mocker.patch.object(
        gpg, "_encr_path2key_fingerprint", return_value=SOME_FINGERPRINT
    )
    mocker.patch.object(gpg, "_get_encrypted_path", return_value=encr_path)
    mocker.patch.object(os.path, "exists", side_effect=(src_exists1, src_exists2))
    if expect == "success":
        ret = gpg_space.move_to_storage_service(src_path, dst_path, None)
        assert ret is None
    else:
        with pytest.raises(gpg.GPGException) as excinfo:
            gpg_space.move_to_storage_service(src_path, dst_path, None)
        if not encr_path:
            assert (
                "Unable to move {}; this file/dir does not exist;"
                " nor is it in an encrypted directory.".format(src_path)
                == str(excinfo.value)
            )
        if not src_exists2:
            assert (
                "Unable to move {}; this file/dir does not"
                " exist, not even in encrypted directory"
                " {}.".format(src_path, encr_path) == str(excinfo.value)
            )
    if src_exists2 and encr_path:
        gpg_space.space.move_rsync.assert_called_once_with(src_path, dst_path)
    else:
        assert not gpg_space.space.move_rsync.called
    if src_exists1:
        gpg._gpg_decrypt.assert_called_once_with(dst_path)
        assert not gpg._gpg_encrypt.called
    else:
        gpg._get_encrypted_path.assert_called_once_with(src_path)
        if encr_path:
            gpg._gpg_encrypt.assert_called_once_with(encr_path, SOME_FINGERPRINT)
            gpg._gpg_decrypt.assert_called_once_with(encr_path)
    gpg_space.space.create_local_directory.assert_called_once_with(dst_path)


@pytest.mark.parametrize(
    "src_path, dst_path, package, encrypt_ret, expect",
    [
        MoveFromCase(
            src_path="/a/b/c/",
            dst_path="/x/y/z",
            package=MockPackage(),
            encrypt_ret=("", ENCRYPT_RET_SUCCESS),
            expect="success",
        ),
        MoveFromCase(
            src_path="/a/b/c/",
            dst_path="/x/y/z",
            package=MockPackage(should_have_pointer=False),
            encrypt_ret=("", ENCRYPT_RET_SUCCESS),
            expect="success",
        ),
        MoveFromCase(
            src_path="/a/b/c/",
            dst_path="/x/y/z",
            package=MockPackage(fingerprint=SOME_OTHER_FINGERPRINT),
            encrypt_ret=("", ENCRYPT_RET_SUCCESS),
            expect="success",
        ),
        MoveFromCase(
            src_path="/a/b/c/",
            dst_path="/x/y/z",
            package=MockPackage(),
            encrypt_ret=gpg.GPGException("gotcha!"),
            expect="fail",
        ),
        MoveFromCase(
            src_path="/a/b/c/",
            dst_path="/x/y/z",
            package=None,
            encrypt_ret=("", ENCRYPT_RET_SUCCESS),
            expect="fail",
        ),
    ],
)
def test_move_from_storage_service(
    mocker, src_path, dst_path, package, encrypt_ret, expect
):
    mocker.patch("locations.models.gpg._get_gpg_version", return_value=GPG_VERSION)
    orig_pkg_key = package and package.encryption_key_fingerprint
    if isinstance(encrypt_ret, Exception):
        mocker.patch.object(gpg, "_gpg_encrypt", side_effect=encrypt_ret)
    else:
        mocker.patch.object(gpg, "_gpg_encrypt", return_value=encrypt_ret)
    gpg_space = gpg.GPG(key=SOME_FINGERPRINT, space=space.Space())
    mocker.patch.object(gpg_space.space, "create_local_directory")
    mocker.patch.object(gpg_space.space, "move_rsync")
    encryption_event = 42
    mocker.patch(
        "locations.models.gpg.premis.create_encryption_event",
        return_value=encryption_event,
    )
    if expect == "success":
        ret = gpg_space.move_from_storage_service(src_path, dst_path, package=package)
        if package.should_have_pointer_file():
            assert ret.events == [encryption_event]
            assert callable(ret.composition_level_updater)
            assert ret.inhibitors[0][0] == "inhibitors"
        else:
            assert ret is None
        if orig_pkg_key != gpg_space.key:
            assert package.encryption_key_fingerprint == gpg_space.key
            assert package.save_called == 1
    else:
        with pytest.raises(gpg.GPGException) as excinfo:
            gpg_space.move_from_storage_service(src_path, dst_path, package=package)
        if package:
            assert excinfo.value == encrypt_ret
        else:
            assert str(excinfo.value) == "GPG spaces can only contain packages"
    if package:
        gpg_space.space.create_local_directory.assert_called_once_with(dst_path)
        gpg_space.space.move_rsync.assert_any_call(
            src_path, dst_path, try_mv_local=True
        )
        if expect != "success":
            gpg_space.space.move_rsync.assert_any_call(
                dst_path, src_path, try_mv_local=True
            )
        gpg._gpg_encrypt.assert_called_once_with(dst_path, gpg_space.key)


@pytest.mark.parametrize(
    "path, encr_path, exists_after_decrypt, expect",
    [
        BrowseCase(
            path="/a/b/c/", encrpath="/a/b/c", existsafter=True, expect="success"
        ),
        BrowseCase(
            path="/a/b/c/somefile.jpg",
            encrpath="/a/b/c",
            existsafter=True,
            expect="success",
        ),
        BrowseCase(
            path="/a/b/c/somefile.jpg", encrpath=None, existsafter=False, expect="fail"
        ),
        BrowseCase(path="/a/b/c/", encrpath="/a/b/c", existsafter=False, expect="fail"),
    ],
)
def test_browse(mocker, path, encr_path, exists_after_decrypt, expect):
    mocker.patch.object(gpg, "_get_encrypted_path", return_value=encr_path)
    mocker.patch.object(gpg, "_gpg_decrypt")
    mocker.patch.object(gpg, "_gpg_encrypt")
    mocker.patch.object(
        gpg, "_encr_path2key_fingerprint", return_value=SOME_FINGERPRINT
    )
    mocker.patch.object(os.path, "exists", return_value=exists_after_decrypt)
    mocker.patch.object(space, "path2browse_dict", return_value=expect)
    fixed_path = path.rstrip("/")
    ret = gpg.GPG().browse(path)
    if expect == "success":
        assert ret == expect
    else:
        assert ret == BROWSE_FAIL_DICT
    gpg._get_encrypted_path.assert_called_once_with(fixed_path)
    if encr_path:
        gpg._gpg_decrypt.assert_called_once_with(encr_path)
        gpg._encr_path2key_fingerprint.assert_called_once_with(encr_path)
        gpg._gpg_encrypt.assert_called_once_with(encr_path, SOME_FINGERPRINT)


@pytest.mark.parametrize(
    "path, isdir, encr_path_is_file, encrypt_ret, expected",
    [
        EncryptCase(
            path="/a/b/c",
            isdir=True,
            encrpathisfile=True,
            encryptret=ENCRYPT_RET_SUCCESS,
            expected="success",
        ),
        EncryptCase(
            path="/a/b/c",
            isdir=False,
            encrpathisfile=True,
            encryptret=ENCRYPT_RET_SUCCESS,
            expected="success",
        ),
        EncryptCase(
            path="/a/b/c",
            isdir=True,
            encrpathisfile=False,
            encryptret=ENCRYPT_RET_SUCCESS,
            expected="fail",
        ),
        EncryptCase(
            path="/a/b/c",
            isdir=True,
            encrpathisfile=True,
            encryptret=ENCRYPT_RET_FAIL,
            expected="fail",
        ),
    ],
)
def test__gpg_encrypt(mocker, path, isdir, encr_path_is_file, encrypt_ret, expected):
    encr_path = f"{path}.gpg"
    mocker.patch.object(os.path, "isdir", return_value=isdir)
    mocker.patch.object(os, "remove")
    mocker.patch.object(os, "rename")
    mocker.patch.object(utils, "create_tar")
    mocker.patch.object(utils, "extract_tar")
    mocker.patch.object(
        gpgutils, "gpg_encrypt_file", return_value=(encr_path, encrypt_ret)
    )
    mocker.patch.object(os.path, "isfile", return_value=encr_path_is_file)
    if expected == "success":
        ret = gpg._gpg_encrypt(path, SOME_FINGERPRINT)
        os.remove.assert_called_once_with(path)
        os.rename.assert_called_once_with(encr_path, path)
        assert ret == (path, encrypt_ret)
        assert not utils.extract_tar.called
    else:
        with pytest.raises(gpg.GPGException) as excinfo:
            gpg._gpg_encrypt(path, SOME_FINGERPRINT)
        assert f"An error occured when attempting to encrypt {path}" == str(
            excinfo.value
        )
        if isdir:
            utils.extract_tar.assert_called_once_with(path)
    os.path.isdir.assert_called_once_with(path)
    os.path.isfile.assert_called_once_with(encr_path)
    if isdir:
        utils.create_tar.assert_called_once_with(path)


def test__get_encrypted_path(monkeypatch):
    def mock_isfile(path):
        return path in ("/a/b/c", "/a/b/d")

    monkeypatch.setattr(os.path, "isfile", mock_isfile)
    assert gpg._get_encrypted_path("/some/silly/path") is None
    assert gpg._get_encrypted_path("/a/b/c") == "/a/b/c"
    assert gpg._get_encrypted_path("/a/b/c/d/e") == "/a/b/c"
    assert gpg._get_encrypted_path("/a/b/d/f/h") == "/a/b/d"
    assert gpg._get_encrypted_path("/a/b") is None


@pytest.mark.parametrize(
    "path, isfile, will_create_decrypt_file, decrypt_ret, expected",
    [
        DecryptCase(
            path="/a/b/c",
            isfile=True,
            createsdecryptfile=True,
            decryptret=DECRYPT_RET_SUCCESS,
            expected="success",
        ),
        DecryptCase(
            path="/x/y/z",
            isfile=False,
            createsdecryptfile=False,
            decryptret=DECRYPT_RET_FAIL,
            expected="fail",
        ),
        DecryptCase(
            path="/a/b/c",
            isfile=True,
            createsdecryptfile=False,
            decryptret=DECRYPT_RET_FAIL,
            expected="fail",
        ),
    ],
)
def test__gpg_decrypt(
    mocker, path, isfile, will_create_decrypt_file, decrypt_ret, expected
):
    mocker.patch("os.remove")
    mocker.patch("os.rename")
    mocker.patch.object(tarfile, "is_tarfile", return_value=True)
    mocker.patch.object(gpgutils, "gpg_decrypt_file", return_value=decrypt_ret)
    mocker.patch.object(utils, "extract_tar")

    def isfilemock(path_):
        if path_ == path:
            return isfile
        return will_create_decrypt_file

    mocker.patch.object(os.path, "isfile", side_effect=isfilemock)
    assert not gpgutils.gpg_decrypt_file.called
    decr_path = f"{path}.decrypted"
    if expected == "success":
        ret = gpg._gpg_decrypt(path)
        os.remove.assert_called_once_with(path)
        os.rename.assert_called_once_with(decr_path, path)
        tarfile.is_tarfile.assert_called_once_with(path)
        utils.extract_tar.assert_called_once_with(path)
        assert ret == path
    else:
        with pytest.raises(gpg.GPGException) as excinfo:
            gpg._gpg_decrypt(path)
        if isfile:
            assert "Failed to decrypt {}. Reason: {}".format(
                path, DECRYPT_RET_FAIL_STATUS
            ) == str(excinfo.value)
        else:
            assert f"Cannot decrypt file at {path}; no such file." == str(excinfo.value)
        assert not os.remove.called
        assert not os.rename.called
        assert not tarfile.is_tarfile.called
        assert not utils.extract_tar.called
    if isfile:
        gpgutils.gpg_decrypt_file.assert_called_once_with(path, decr_path)
    else:
        assert not gpgutils.gpg_decrypt_file.called


def test__parse_gpg_version():
    assert GPG_VERSION == gpg._parse_gpg_version(RAW_GPG_VERSION)


class TestGPG(TestCase):

    fixtures = ["base.json", "package.json", "gpg.json"]

    def test__encr_path2key_fingerprint(self):
        package = Package.objects.get(pk=8)
        exp_curr_path = (
            "some/relative/path/to/"
            "images-transfer-abcdabcd-97dd-48e0-8417-03be78359531"
        )
        assert package.current_path == exp_curr_path
        assert package.encryption_key_fingerprint == EXP_FINGERPRINT

        encr_path = exp_curr_path
        assert gpg._encr_path2key_fingerprint(encr_path) == EXP_FINGERPRINT

        encr_path = f"/abs/path/to/{exp_curr_path}"
        assert gpg._encr_path2key_fingerprint(encr_path) == EXP_FINGERPRINT

        encr_path = f"{exp_curr_path}/data/objects/somefile.jpg"
        assert gpg._encr_path2key_fingerprint(encr_path) == EXP_FINGERPRINT

        encr_path = f"/abs/path/to/{exp_curr_path}/data/objects/somefile.jpg"
        assert gpg._encr_path2key_fingerprint(encr_path) == EXP_FINGERPRINT

        with pytest.raises(gpg.GPGException) as excinfo:
            encr_path = "/some/non/matching/path.jpg"
            gpg._encr_path2key_fingerprint(encr_path)
        assert "Unable to find package matching encrypted path {}".format(
            encr_path
        ) in str(excinfo.value)
