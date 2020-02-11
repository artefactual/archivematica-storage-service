from __future__ import absolute_import
import pytest
from scandir import scandir

from locations.models.space import path2browse_dict


def _restrict_access_to(restricted_path):
    """Simulate OSError raised by scandir when it cannot access a path."""

    def scandir_mock(path):
        if path == restricted_path:
            raise OSError("Permission denied: '{}'".format(path))
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
    mocker.patch("scandir.scandir", side_effect=_restrict_access_to(tree.join("empty")))
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
    mocker.patch("scandir.scandir", side_effect=_restrict_access_to(tree.join("first")))
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
    mocker.patch(
        "scandir.scandir", side_effect=_restrict_access_to(tree.join("second"))
    )
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
        "scandir.scandir",
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
