import os
from os import scandir
import subprocess

import pytest
import shutil

from locations.models import Space
from locations.models.space import path2browse_dict


def _restrict_access_to(restricted_path):
    """Simulate OSError raised by scandir when it cannot access a path."""

    def scandir_mock(path):
        if path == restricted_path:
            raise OSError(f"Permission denied: '{path}'")
        return scandir(path)

    return scandir_mock


@pytest.fixture
def tree(tmpdir):
    """Create a directory structure like:
    - tree
      + empty
      - error.txt
      + first
        - first_a.txt
        - first_b.txt
      + second
        - second_a.txt
        + third
          - third_a.txt
      - tree_a.txt
    """
    result = tmpdir.mkdir("tree")
    result.mkdir("empty")
    first = result.mkdir("first")
    first_a = first.join("first_a.txt")
    first_a.write("first A")
    first_b = first.join("first_B.txt")
    first_b.write("first B")
    second = result.mkdir("second")
    second_a = second.join("second_a.txt")
    second_a.write("second A")
    third_a = second.mkdir("third").join("third_a.txt")
    third_a.write("third A")
    tree_a = result.join("tree_a.txt")
    tree_a.write("tree A")
    error = result.join("error.txt")
    error.write("error!!!")
    return result


def test_path2browse_dict_object_counting_ignores_read_protected_directories(
    tree, mocker
):
    # Enable object counting in spaces.
    mocker.patch("common.utils.get_setting", return_value=False)

    # Count objects in the tree without access restrictions.
    result = path2browse_dict(str(tree))
    assert result == {
        "directories": ["empty", "first", "second"],
        "entries": ["empty", "error.txt", "first", "second", "tree_a.txt"],
        "properties": {
            "empty": {"object count": 0},
            "error.txt": {"size": 8},
            "first": {"object count": 2},
            "second": {"object count": 2},
            "tree_a.txt": {"size": 6},
        },
    }

    # Restrict read access to the "empty" directory.
    mocker.patch("os.scandir", side_effect=_restrict_access_to(tree.join("empty")))
    assert path2browse_dict(str(tree)) == {
        "directories": ["empty", "first", "second"],
        "entries": ["empty", "error.txt", "first", "second", "tree_a.txt"],
        "properties": {
            "empty": {"object count": 0},
            "error.txt": {"size": 8},
            "first": {"object count": 2},
            "second": {"object count": 2},
            "tree_a.txt": {"size": 6},
        },
    }

    # Restrict read access to the "first" directory.
    mocker.patch("os.scandir", side_effect=_restrict_access_to(tree.join("first")))
    assert path2browse_dict(str(tree)) == {
        "directories": ["empty", "first", "second"],
        "entries": ["empty", "error.txt", "first", "second", "tree_a.txt"],
        "properties": {
            "empty": {"object count": 0},
            "error.txt": {"size": 8},
            "first": {"object count": 0},
            "second": {"object count": 2},
            "tree_a.txt": {"size": 6},
        },
    }

    # Restrict read access to the "second" directory.
    mocker.patch("os.scandir", side_effect=_restrict_access_to(tree.join("second")))
    assert path2browse_dict(str(tree)) == {
        "directories": ["empty", "first", "second"],
        "entries": ["empty", "error.txt", "first", "second", "tree_a.txt"],
        "properties": {
            "empty": {"object count": 0},
            "error.txt": {"size": 8},
            "first": {"object count": 2},
            "second": {"object count": 0},
            "tree_a.txt": {"size": 6},
        },
    }

    # Restrict read access to the "third" directory (child of the "second" directory).
    mocker.patch(
        "os.scandir",
        side_effect=_restrict_access_to(tree.join("second").join("third")),
    )
    assert path2browse_dict(str(tree)) == {
        "directories": ["empty", "first", "second"],
        "entries": ["empty", "error.txt", "first", "second", "tree_a.txt"],
        "properties": {
            "empty": {"object count": 0},
            "error.txt": {"size": 8},
            "first": {"object count": 2},
            "second": {"object count": 1},
            "tree_a.txt": {"size": 6},
        },
    }


# AIP store directory structure with components of the quad structure
# we're generating created specifically to share branches which pushes
# the limit of "probability", but is not impossible.
P1 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888")
P2 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666", "8888", "9999")
P3 = os.path.join("1111", "2222", "3333", "4444", "5555", "8888", "9999", "aaaa")
P4 = os.path.join("1111", "2222", "3333", "4444", "8888", "9999", "aaaa", "bbbb")
P5 = os.path.join("1111", "2222", "3333", "8888", "9999", "aaaa", "bbbb", "cccc")
P6 = os.path.join("1111", "2222", "8888", "9999", "aaaa", "bbbb", "cccc", "dddd")
P7 = os.path.join("1111", "8888", "9999", "aaaa", "bbbb", "cccc", "eeee", "eeee")

# Once deleted per AIP at each location, the following paths should
# remain, R = Remain.
R1 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666")
R2 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666")
R3 = os.path.join("1111", "2222", "3333", "4444", "5555")
R4 = os.path.join("1111", "2222", "3333", "4444")
R5 = os.path.join("1111", "2222", "3333")
R6 = os.path.join("1111", "2222")
R7 = os.path.join("1111")

# Once deleted per AIP at each location, the following paths should be
# deleted, D = Deleted.
D1 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666", "7777")
D2 = os.path.join("1111", "2222", "3333", "4444", "5555", "6666", "8888")
D3 = os.path.join("1111", "2222", "3333", "4444", "5555", "8888")
D4 = os.path.join("1111", "2222", "3333", "4444", "8888")
D5 = os.path.join("1111", "2222", "3333", "8888")
D6 = os.path.join("1111", "2222", "8888")
D7 = os.path.join("1111", "8888")

# Compressed or "packaged" AIP names to combine with the AIPstore dirs.
C1 = "0a-11112222-3333-4444-5555-666677778888.7z"
C2 = "0b-11112222-3333-4444-5555-666688889999.7z"
C3 = "0c-11112222-3333-4444-5555-88889999aaaa.7z"
C4 = "0d-11112222-3333-4444-8888-9999aaaabbbb.7z"
C5 = "0e-11112222-3333-8888-9999-aaaabbbbcccc.7z"
C6 = "0f-11112222-8888-9999-aaaa-bbbbccccdddd.tar.gz"
C7 = "1a-11118888-9999-aaaa-bbbb-cccceeeeeeee.zip"

MAGIC = "\x37\x7A\xBC\xAF\x27\x1C"

AIPSTORE = "AIPstore"

# Pair paths with AIP names. The P{no} prefix is used to simplify
# the quad-path and the C{no} prefix is used to simplify the
# compressed package directory.
COMPRESSED_AIPS = [(P1, C1), (P2, C2), (P3, C3), (P4, C4), (P5, C5), (P6, C6), (P7, C7)]


@pytest.fixture
def aipstore_compressed(tmpdir):
    """Create a structure simulating an AIPstore with an appropriate
    level of complexity.

    i.e.

        └── 1111
            ├── 2222
            │   ├── 3333
            │   │   ├── 4444
            │   │   │   ├── 5555
            │   │   │   │   ├── 6666
            │   │   │   │   │   ├── 7777
            │   │   │   │   │   │   └── 8888
            │   │   │   │   │   │       └── 0a-11112222-3333-4444-5555-666677778888.7z
            │   │   │   │   │   └── 8888
            │   │   │   │   │       └── 9999
            │   │   │   │   │   │       └── etc.
            │   │   │   │   └── 8888
            │   │   │   │       └── 9999
            │   │   │   │           └── aaaa
            │   │   │   └── 8888
            │   │   │       └── 9999
            │   │   │           └── aaaa
            │   │   │               └── bbbb
            │   │   └── 8888
            │   │       └── 9999
            │   │           └── aaaa
            │   │               └── bbbb
            │   │                   └── cccc
            │   └── 8888
            │       └── 9999
            │           └── aaaa
            │               └── bbbb
            │                   └── cccc
            │                       └── dddd
            └── 8888
                └── 9999
                    └── aaaa
                        └── bbbb
                            └── cccc
                                └── eeee
                                    └── eeee

    which is created using the following paths which we list to help
    manual verification of this effort outside of pytest:

        1111/2222/3333/4444/5555/6666/7777/8888/0a-11112222-3333-4444-5555-666677778888.7z
        1111/2222/3333/4444/5555/6666/8888/9999/0b-11112222-3333-4444-5555-666688889999.7z
        1111/2222/3333/4444/5555/8888/9999/aaaa/0c-11112222-3333-4444-5555-88889999aaaa.7z
        1111/2222/3333/4444/8888/9999/aaaa/bbbb/0d-11112222-3333-4444-8888-9999aaaabbbb.7z
        1111/2222/3333/8888/9999/aaaa/bbbb/cccc/0e-11112222-3333-8888-9999-aaaabbbbcccc.7z
        1111/2222/8888/9999/aaaa/bbbb/cccc/dddd/0f-11112222-8888-9999-aaaa-bbbbccccdddd.tar.gz
        1111/8888/9999/aaaa/bbbb/cccc/eeee/eeee/1a-11118888-9999-aaaa-bbbb-cccceeeeeeee.zip

    The quad-structure is described in the documentation:

        * Docs: https://git.io/JLP2b

    :returns: (path to AIPstore (py.path, list of all paths, package
        file (tuple)} (tuple)
    """
    aipstore = tmpdir.mkdir(AIPSTORE)
    aipstore_path = str(aipstore)

    AIP_QUAD_PATH = 0
    COMPRESSED_PACKAGE_DIR = 1

    for path in COMPRESSED_AIPS:
        path_to_write_to = os.path.join(aipstore_path, path[AIP_QUAD_PATH])
        os.makedirs(path_to_write_to)
        package_file = os.path.join(
            aipstore_path, path[AIP_QUAD_PATH], path[COMPRESSED_PACKAGE_DIR]
        )
        with open(package_file, "wb") as package:
            package.write(MAGIC.encode("utf8"))
        assert os.path.exists(package_file)
        assert os.path.isfile(package_file)

    return aipstore


@pytest.mark.parametrize(
    "path, aip_name, remaining_directory, deleted_directory",
    [
        (P1, C1, R1, D1),
        (P2, C2, R2, D2),
        (P3, C3, R3, D3),
        (P4, C4, R4, D4),
        (P5, C5, R5, D5),
        (P6, C6, R6, D6),
        (P7, C7, R7, D7),
    ],
)
def test_delete_compressed_path_local(
    aipstore_compressed, path, aip_name, mocker, remaining_directory, deleted_directory
):
    """Test that local compressed or packaged paths e.g. tar.gz are
    deleted as expected.
    """

    # Initialize our space and create a path to delete.
    sp = Space()
    path_to_delete = os.path.join(str(aipstore_compressed), path, aip_name)

    # rmtree is used to delete directories, we want to make sure we
    # don't call it from the delete function.
    mocker.patch("shutil.rmtree", side_effect=shutil.rmtree)

    # Make sure there is something to delete and delete it.
    assert os.path.exists(path_to_delete)
    sp._delete_path_local(path_to_delete)

    # Verify that we called shutil was not called to remove a file.
    shutil.rmtree.assert_not_called()

    # Make sure the path is gone.
    assert not os.path.exists(path_to_delete)

    # Make sure that the AIPSTORE part of the path is preserved.
    aipstore = str(aipstore_compressed).split(path, 1)[0]
    assert os.path.exists(aipstore)

    # Assert none of the other AIPs have been deleted as a result of
    # the function.
    assert len(COMPRESSED_AIPS) > 0
    for aip_path, filename in COMPRESSED_AIPS:
        remaining_aip = os.path.join(aip_path, filename)
        test_dir = os.path.join(path, aip_name)
        if remaining_aip == test_dir:
            continue
        remaining_aip = os.path.join(str(aipstore_compressed), remaining_aip)
        assert os.path.exists(remaining_aip)
        assert os.path.isfile(remaining_aip)

    # Ensure that the correct parts of the quad-directory structure
    # remain.
    assert os.path.exists(os.path.join(aipstore, remaining_directory))
    assert not os.path.exists(os.path.join(aipstore, deleted_directory))


# Uncompressed AIP names to combine with the AIPstore dirs.
U1 = "0a-11112222-3333-4444-5555-666677778888"
U2 = "0b-11112222-3333-4444-5555-666688889999"
U3 = "0c-11112222-3333-4444-5555-88889999aaaa"
U4 = "0d-11112222-3333-4444-8888-9999aaaabbbb"
U5 = "0e-11112222-3333-8888-9999-aaaabbbbcccc"
U6 = "0f-11112222-8888-9999-aaaa-bbbbccccdddd"
U7 = "1a-11118888-9999-aaaa-bbbb-cccceeeeeeee"

# Pair paths with AIP names. The P{no} prefix is used to simplify
# the quad-path and the U{no} prefix is used to simplify the
# uncompressed package directory.
UNCOMPRESSED_AIPS = [
    (P1, U1),
    (P2, U2),
    (P3, U3),
    (P4, U4),
    (P5, U5),
    (P6, U6),
    (P7, U7),
]


@pytest.fixture
def aipstore_uncompressed(tmpdir):
    """Create a structure simulating an AIPstore with an appropriate
    level of complexity.

    i.e.

        └── 1111
            ├── 2222
            │   ├── 3333
            │   │   ├── 4444
            │   │   │   ├── 5555
            │   │   │   │   ├── 6666
            │   │   │   │   │   ├── 7777
            │   │   │   │   │   │   └── 8888
            │   │   │   │   │   │       └── 0a-11112222-3333-4444-5555-666677778888
            │   │   │   │   │   └── 8888
            │   │   │   │   │       └── 9999
            │   │   │   │   │   │       └── etc.
            │   │   │   │   └── 8888
            │   │   │   │       └── 9999
            │   │   │   │           └── aaaa
            │   │   │   └── 8888
            │   │   │       └── 9999
            │   │   │           └── aaaa
            │   │   │               └── bbbb
            │   │   └── 8888
            │   │       └── 9999
            │   │           └── aaaa
            │   │               └── bbbb
            │   │                   └── cccc
            │   └── 8888
            │       └── 9999
            │           └── aaaa
            │               └── bbbb
            │                   └── cccc
            │                       └── dddd
            └── 8888
                └── 9999
                    └── aaaa
                        └── bbbb
                            └── cccc
                                └── eeee
                                    └── eeee

    which is created using the following paths which we list to help
    manual verification of this effort outside of pytest:

        1111/2222/3333/4444/5555/6666/7777/8888/0a-11112222-3333-4444-5555-666677778888/some-manifest
        1111/2222/3333/4444/5555/6666/8888/9999/0b-11112222-3333-4444-5555-666688889999/some-manifest
        1111/2222/3333/4444/5555/8888/9999/aaaa/0c-11112222-3333-4444-5555-88889999aaaa/some-manifest
        1111/2222/3333/4444/8888/9999/aaaa/bbbb/0d-11112222-3333-4444-8888-9999aaaabbbb/some-manifest
        1111/2222/3333/8888/9999/aaaa/bbbb/cccc/0e-11112222-3333-8888-9999-aaaabbbbcccc/some-manifest
        1111/2222/8888/9999/aaaa/bbbb/cccc/dddd/0f-11112222-8888-9999-aaaa-bbbbccccdddd/some-manifest
        1111/8888/9999/aaaa/bbbb/cccc/eeee/eeee/1a-11118888-9999-aaaa-bbbb-cccceeeeeeee/some-manifest

    The quad-structure is described in the documentation:

        * Docs: https://git.io/JLP2b

    :returns: (path to AIPstore (py.path, list of all paths, package
        dirs (tuple)} (tuple)
    """
    aipstore = tmpdir.mkdir(AIPSTORE)
    aipstore_path = str(aipstore)

    some_file_name = "some-manifest"
    some_data = "some_data"

    for path, aip_name in UNCOMPRESSED_AIPS:
        # Write some data to simulate an actual package in the storage
        # service.
        path_to_write_to = os.path.join(aipstore_path, path, aip_name)
        os.makedirs(path_to_write_to)
        some_file = os.path.join(aipstore_path, path, aip_name, some_file_name)
        with open(some_file, "wb") as _some_file:
            _some_file.write(some_data.encode("utf8"))
        assert os.path.exists(some_file)

    return aipstore


@pytest.mark.parametrize(
    "path, aip_name, remaining_directory, deleted_directory",
    [
        (P1, U1, R1, D1),
        (P2, U2, R2, D2),
        (P3, U3, R3, D3),
        (P4, U4, R4, D4),
        (P5, U5, R5, D5),
        (P6, U6, R6, D6),
        (P7, U7, R7, D7),
    ],
)
def test_delete_uncompressed_path_local(
    aipstore_uncompressed,
    path,
    aip_name,
    remaining_directory,
    deleted_directory,
    mocker,
):
    """Test that local uncompressed paths are deleted as expected."""

    # Initialize our space and create a path to delete.
    sp = Space()
    path_to_delete = os.path.join(str(aipstore_uncompressed), path, aip_name)

    # rmtree is used to delete directories, we want to make sure we
    # do call it from the delete function.
    mocker.patch("shutil.rmtree", side_effect=shutil.rmtree)

    # Make sure there is something to delete and delete it.
    assert os.path.exists(path_to_delete)
    sp._delete_path_local(path_to_delete)

    # Verify that we called shutil to remove a directory, not a file.
    shutil.rmtree.assert_called_with(path_to_delete)

    # Make sure the path is gone.
    assert not os.path.exists(path_to_delete)

    # Make sure that the AIPSTORE part of the path is preserved.
    aipstore = str(aipstore_uncompressed).split(path, 1)[0]
    assert os.path.exists(aipstore)

    # Assert none of the other AIPs have been deleted as a result of
    # the function.
    assert len(UNCOMPRESSED_AIPS) > 0
    for aip_path, filename in UNCOMPRESSED_AIPS:
        remaining_aip = os.path.join(aip_path, filename)
        test_dir = os.path.join(path, aip_name)
        if remaining_aip == test_dir:
            continue
        remaining_aip = os.path.join(str(aipstore_uncompressed), remaining_aip)
        assert os.path.exists(remaining_aip)
        # Ensure the package contains our simple manifest sample data.
        assert len(os.listdir(remaining_aip)) == 1
        assert os.listdir(remaining_aip)[0] == "some-manifest"

    # Ensure that the correct parts of the quad-directory structure
    # remain.
    assert os.path.exists(os.path.join(aipstore, remaining_directory))
    assert not os.path.exists(os.path.join(aipstore, deleted_directory))


def test_delete_non_existant_path_local(tmpdir, aipstore_uncompressed):
    """Test the behavior when deleting non-existent paths and ensure
    that when this is attempted there are no negative effects on the
    AIP store.
    """

    # Initialize our space and create a path to delete.
    sp = Space()
    path_to_delete = os.path.join(str(tmpdir), "does-not-exist")

    # Make sure the path is essentially a nonsense path.
    assert not os.path.exists(path_to_delete)

    # There is no specific behavior for a path that doesn't exist, the
    # function will fall through to a return of None.
    assert sp._delete_path_local(path_to_delete) is None

    # However unlikely, and in lieu of any other useful tests, make sure
    # that there are no other side-effects i.e. the AIPstore is not affected.
    assert len(UNCOMPRESSED_AIPS) > 0
    for aip_path, filename in UNCOMPRESSED_AIPS:
        remaining_aip = os.path.join(aip_path, filename)
        remaining_aip = os.path.join(str(aipstore_uncompressed), remaining_aip)
        assert os.path.exists(remaining_aip)


def test_move_rsync_command_decodes_paths(mocker):
    popen = mocker.patch(
        "subprocess.Popen",
        return_value=mocker.Mock(
            **{"communicate.return_value": ("command output", None), "returncode": 0}
        ),
    )
    space = Space()
    space.move_rsync("source_dir", "destination_dir")

    popen.assert_called_once_with(
        [
            "rsync",
            "-t",
            "-O",
            "--protect-args",
            "-vv",
            "--chmod=Fug+rw,o-rwx,Dug+rwx,o-rwx",
            "-r",
            "source_dir",
            "destination_dir",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_create_rsync_directory_commands_decode_paths(tmp_path, mocker):
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    dest_dir = "/a/mock/path/"

    check_call = mocker.patch("subprocess.check_call")
    mocker.patch("tempfile.mkdtemp", return_value=str(temp_dir))

    space = Space()
    space.create_rsync_directory(dest_dir, "user", "host")

    check_call.assert_has_calls(
        [
            mocker.call(
                [
                    "rsync",
                    "-vv",
                    "--protect-args",
                    "--chmod=ug=rwx,o=rx",
                    "--recursive",
                    os.path.join(str(temp_dir), ""),
                    "user@host:/",
                ]
            ),
            mocker.call(
                [
                    "rsync",
                    "-vv",
                    "--protect-args",
                    "--chmod=ug=rwx,o=rx",
                    "--recursive",
                    os.path.join(str(temp_dir), ""),
                    "user@host:/a/",
                ]
            ),
            mocker.call(
                [
                    "rsync",
                    "-vv",
                    "--protect-args",
                    "--chmod=ug=rwx,o=rx",
                    "--recursive",
                    os.path.join(str(temp_dir), ""),
                    "user@host:/a/mock/",
                ]
            ),
            mocker.call(
                [
                    "rsync",
                    "-vv",
                    "--protect-args",
                    "--chmod=ug=rwx,o=rx",
                    "--recursive",
                    os.path.join(str(temp_dir), ""),
                    "user@host:/a/mock/path/",
                ]
            ),
        ]
    )
