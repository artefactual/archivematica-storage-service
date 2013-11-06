#! /usr/bin/env python
# -*- coding: utf-8 -*-
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

# @package archivematica-storage-service
# @author Justin Simpson <jsimpson@artefactual.com>

from setuptools import setup, find_packages

setup(name='archivematica-storage-service',
      packages=find_packages(),
      version='0.2.0',
      author=u'Justin Simpson',
      author_email='jsimpson@artefactual.com',
      url='https://github.com/artefacutal/archivematica-storage-service',
      description='Django based webapp for managing storage in an Archivematica installation',
      license='Affero GNU General Public License v3 or later',
      )
