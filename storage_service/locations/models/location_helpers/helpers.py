# -*- coding: utf-8 -*-

from __future__ import absolute_import

import logging
import os
import shutil
import subprocess
import tarfile

from django.utils.translation import ugettext_lazy as _


LOGGER = logging.getLogger(__name__)


class TARException(Exception):
    pass


def _abort_create_tar(path, tarpath):
    fail_msg = _(
        "Failed to create a tarfile at %(tarpath)s for dir at %(path)s"
        % {"tarpath": tarpath, "path": path}
    )
    LOGGER.error(fail_msg)
    raise TARException(fail_msg)


def create_tar(path):
    """Create a tarfile from the directory at ``path`` and overwrite
    ``path`` with that tarfile.
    """
    path = path.rstrip("/")
    tarpath = "{}.tar".format(path)
    changedir = os.path.dirname(tarpath)
    source = os.path.basename(path)
    cmd = ["tar", "-C", changedir, "-cf", tarpath, source]
    LOGGER.info(
        "creating archive of %s at %s, relative to %s", source, tarpath, changedir
    )
    try:
        subprocess.check_output(cmd)
    except (OSError, subprocess.CalledProcessError):
        _abort_create_tar(path, tarpath)

    # Providing the TAR is successfully created then remove the original.
    if os.path.isfile(tarpath) and tarfile.is_tarfile(tarpath):
        try:
            shutil.rmtree(path)
        except OSError:
            # Remove a file-path as We're likely packaging a file, e.g. 7z.
            os.remove(path)
        os.rename(tarpath, path)
    else:
        _abort_create_tar(path, tarpath)
    try:
        assert tarfile.is_tarfile(path)
        assert not os.path.exists(tarpath)
    except AssertionError:
        _abort_create_tar(path, tarpath)


def _abort_extract_tar(tarpath, newtarpath, err):
    fail_msg = _(
        "Failed to extract %(tarpath)s: %(error)s" % {"tarpath": tarpath, "error": err}
    )
    LOGGER.error(fail_msg)
    os.rename(newtarpath, tarpath)
    raise TARException(fail_msg)


def extract_tar(tarpath):
    """Extract tarfile at ``path`` to a directory at ``path``."""
    newtarpath = "{}.tar".format(tarpath)
    os.rename(tarpath, newtarpath)
    changedir = os.path.dirname(newtarpath)
    cmd = ["tar", "-xf", newtarpath, "-C", changedir]
    try:
        subprocess.check_output(cmd)
    except (OSError, subprocess.CalledProcessError) as err:
        _abort_extract_tar(tarpath, newtarpath, err)
    # TODO: GPG treats this differently because it only ever expects to
    # TAR a directory but we actually want to TAR file-types as well.
    os.remove(newtarpath)
