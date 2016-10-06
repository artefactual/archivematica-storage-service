#
# -*- coding: utf-8 -*-

# Copyright (c) 2016 Ymagis SA, http://www.ymagis.com/
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
#
# @author Thomas Capricelli <capricelli@sylphide-consulting.com>
#



# Usage
# source setupenv
# python testirods.py

# System
import sys
from os.path import join

# Django
import django
django.setup()

# Project
from locations.models.irodsplugin import *


# Must be present in "staging_path", typically "/tmp" for testing
TESTFILE = "irodsplugin.testfile"
TESTDIR_SOURCE = "irodsplugin.testdir.bagit"
TESTDIR_IRODS = "aw/if/hw/fh/aw/oe/fa/ew/fo/awj/17256f80-8080-4b4f-9c2c-85027a39fc31"

TESTFILEBACK = TESTFILE + ".back"
TESTDIRBACK = TESTDIR_SOURCE + ".back"

def browse_home(i):
    d = i.browse("/home/rods")
    directories = d['directories']
    entries = d['entries']
    properties = d['properties']

    print "directories:\n\t", "\n\t".join(directories)
    print "entries:\n\t", "\n\t".join(entries)
    print "properties:"
    for name,prop in properties.iteritems():
        print "\t%s:"%name, prop

def clean_test_file(warn_user=False):
    if TESTFILE not in i.browse("/home/rods")['entries']:
        return
    if warn_user: print "\n%s already exists, removing ..." % TESTFILE,
    i.delete_path(join(i.space.path, TESTFILE))
    if warn_user: print "done"

#
# Unit Tests
#
def test_browse(i):
    print "\nTesting browse: "
    browse_home(i)
    clean_test_file(warn_user=True)

def test_iput(i):
    print "\nTesting _iput"
    local_path, irods_path = i.space._move_from_path_mangling(TESTFILE, TESTFILE)
    i._iput(local_path, irods_path)
#    browse_home(i)

def test_iget(i):
    print "\nTesting _iget"
    local_path, irods_path = i.space._move_from_path_mangling("restored_%s" % TESTFILE, TESTFILE)
    i._iget(irods_path, local_path)

def test_move_from_storage_service_file(i):
    print "\nTesting move_from_storage_service() with a file"
    clean_test_file()
    i.space.move_from_storage_service(TESTFILE, TESTFILE)

def test_move_from_storage_service_dir(i):
    print "\nTesting move_from_storage_service() with a directory"
    i.space.move_from_storage_service(TESTDIR_SOURCE, TESTDIR_IRODS)

def test_move_to_storage_service_file(i):
    print "\nTesting move_to_storage_service() with a file"
    # keep same space for testing
    i.space.move_to_storage_service(TESTFILE, TESTFILEBACK, i.space)

def test_move_to_storage_service_dir(i):
    print "\nTesting move_to_storage_service() with a directory"
    i.space.move_to_storage_service(TESTDIR_IRODS, TESTDIRBACK, i.space)

#
# Main
#

i = iRODS.objects.get(id=2)

test_browse(i)
test_iput(i)
test_iget(i)
test_move_from_storage_service_file(i)
test_move_from_storage_service_dir(i)
test_move_to_storage_service_file(i)
test_move_to_storage_service_dir(i)

