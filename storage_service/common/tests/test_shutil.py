"""Extracted from Python's ``Lib/test/test_shutil.py``."""

import collections
import contextlib
import os
import shutil
import stat
import sys
import tempfile
import unittest

from common.which import which


@contextlib.contextmanager
def change_cwd(path, quiet=False):
    """Return a context manager that changes the current working directory.
    Arguments:
      path: the directory to use as the temporary current working directory.
      quiet: if False (the default), the context manager raises an exception
        on error.  Otherwise, it issues only a warning and keeps the current
        working directory the same.
    """
    saved_dir = os.getcwd()
    try:
        os.chdir(path)
    except OSError:
        if not quiet:
            raise
    try:
        yield os.getcwd()
    finally:
        os.chdir(saved_dir)


class EnvironmentVarGuard(collections.MutableMapping):
    """Class to help protect the environment variable properly.

    It can be used as a context manager.
    """

    def __init__(self):
        self._environ = os.environ
        self._changed = {}

    def __getitem__(self, envvar):
        return self._environ[envvar]

    def __setitem__(self, envvar, value):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        self._environ[envvar] = value

    def __delitem__(self, envvar):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        if envvar in self._environ:
            del self._environ[envvar]

    def keys(self):
        return list(self._environ.keys())

    def __iter__(self):
        return iter(self._environ)

    def __len__(self):
        return len(self._environ)

    def set(self, envvar, value):
        self[envvar] = value

    def unset(self, envvar):
        del self[envvar]

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        for (k, v) in self._changed.items():
            if v is None:
                if k in self._environ:
                    del self._environ[k]
            else:
                self._environ[k] = v
        os.environ = self._environ


class TestWhich(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="Tmp")
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        # Give the temp_file an ".exe" suffix for all.
        # It's needed on Windows and not harmful on other platforms.
        self.temp_file = tempfile.NamedTemporaryFile(
            dir=self.temp_dir, prefix="Tmp", suffix=".Exe"
        )
        os.chmod(self.temp_file.name, stat.S_IXUSR)
        self.addCleanup(self.temp_file.close)
        self.dir, self.file = os.path.split(self.temp_file.name)

    def test_basic(self):
        # Given an EXE in a directory, it should be returned.
        rv = which(self.file, path=self.dir)
        self.assertEqual(rv, self.temp_file.name)

    def test_absolute_cmd(self):
        # When given the fully qualified path to an executable that exists,
        # it should be returned.
        rv = which(self.temp_file.name, path=self.temp_dir)
        self.assertEqual(rv, self.temp_file.name)

    def test_relative_cmd(self):
        # When given the relative path with a directory part to an executable
        # that exists, it should be returned.
        base_dir, tail_dir = os.path.split(self.dir)
        relpath = os.path.join(tail_dir, self.file)
        with change_cwd(path=base_dir):
            rv = which(relpath, path=self.temp_dir)
            self.assertEqual(rv, relpath)
        # But it shouldn't be searched in PATH directories (issue #16957).
        with change_cwd(path=self.dir):
            rv = which(relpath, path=base_dir)
            self.assertIsNone(rv)

    def test_cwd(self):
        # Issue #16957
        base_dir = os.path.dirname(self.dir)
        with change_cwd(path=self.dir):
            rv = which(self.file, path=base_dir)
            if sys.platform == "win32":
                # Windows: current directory implicitly on PATH
                self.assertEqual(rv, os.path.join(os.curdir, self.file))
            else:
                # Other platforms: shouldn't match in the current directory.
                self.assertIsNone(rv)

    @unittest.skipIf(
        hasattr(os, "geteuid") and os.geteuid() == 0, "non-root user required"
    )
    def test_non_matching_mode(self):
        # Set the file read-only and ask for writeable files.
        os.chmod(self.temp_file.name, stat.S_IREAD)
        if os.access(self.temp_file.name, os.W_OK):
            self.skipTest("can't set the file read-only")
        rv = which(self.file, path=self.dir, mode=os.W_OK)
        self.assertIsNone(rv)

    def test_relative_path(self):
        base_dir, tail_dir = os.path.split(self.dir)
        with change_cwd(path=base_dir):
            rv = which(self.file, path=tail_dir)
            self.assertEqual(rv, os.path.join(tail_dir, self.file))

    def test_nonexistent_file(self):
        # Return None when no matching executable file is found on the path.
        rv = which("foo.exe", path=self.dir)
        self.assertIsNone(rv)

    @unittest.skipUnless(sys.platform == "win32", "pathext check is Windows-only")
    def test_pathext_checking(self):
        # Ask for the file without the ".exe" extension, then ensure that
        # it gets found properly with the extension.
        rv = which(self.file[:-4], path=self.dir)
        self.assertEqual(rv, self.temp_file.name[:-4] + ".EXE")

    def test_environ_path(self):
        with EnvironmentVarGuard() as env:
            env["PATH"] = self.dir
            rv = which(self.file)
            self.assertEqual(rv, self.temp_file.name)

    def test_empty_path(self):
        with change_cwd(path=self.dir):
            with EnvironmentVarGuard() as env:
                env["PATH"] = self.dir
                rv = which(self.file, path="")
                self.assertIsNone(rv)

    def test_empty_path_no_PATH(self):
        with EnvironmentVarGuard() as env:
            env.pop("PATH", None)
            rv = which(self.file)
            self.assertIsNone(rv)
