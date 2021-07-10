#! /usr/bin/env python

# Copyright (c) 2013 Artefactual Systems Inc. http://www.artefactual.com
#
# This file is part of archivematica-storage-service.

# archivematica-storage-service is free software: you can redistribute it
# and/or modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# archivematica-storage-service is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with archivematica-storage-service.  If not,
# see <http://www.gnu.org/licenses/>.

import codecs
import os
import re

from setuptools import setup


def read(*parts):
    path = os.path.join(os.path.dirname(__file__), *parts)
    with codecs.open(path, encoding="utf-8") as fobj:
        return fobj.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="archivematica-storage-service",
    packages=["storage_service"],
    version=find_version("storage_service", "storage_service", "__init__.py"),
    author="Artefactual Systems Inc",
    author_email="info@artefactual.com",
    url="https://github.com/artefacutal/archivematica-storage-service",
    description="Django based webapp for managing storage in an Archivematica installation",
    license="Affero GNU General Public License v3 or later",
)
