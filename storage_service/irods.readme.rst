#
# -*- coding: utf-8 -*-


About the iRODS plugin
----------------------

This plugin allows the archivematica storage service to talk to an
iRODS backend

    http://irods.org/

It is based on the official python bindings for irods :

    https://github.com/irods/python-irodsclient

Unfortunately, there hasn't been any release for very long, despite
development being done. The last relase (0.4.0) dosn't have the required
features needed by this plugin.

This was developed and tested using
* archivematica 1.5
* archivematica storage service 0.8
* python-irodsclient checkout as of april 2016

Features
--------
All plugin methods are implemented (browse, sending files, getting files,
deleting files).

Reading/writing is streamed, which means the plugin can handle very big
files seamlessly without clogging memory.

Checksums
---------
iRODS can store a checksum for each file. This is not mandatory, please
refer to iRODS documentation for more information.

When reading a file from iRODS, if a checksum is provided, the plugin will
check it once the file is read.

When writing a file to iRODS, once finished, the plugin will ask iRODS for
a checksum, and if available, will check against the source/local copy.

iRODS can be configured to automatically compute and attach the checksum
metatada when a file is written.

Altogether, with iRODS properly configured, this allow end-to-end checking
for file corruption, for both reading and writing.

Performance
-----------
Currently, the performance of the python-irodsclient are far less good
than, for example, the command line 'iput/iget' utilities. This is because
features like "parallel transfer" or "automatic direct connection with
resource server" are not implemented.

This will probably only hurt people trying to send a lot of data through
the plugin. Lot being either:
* more than one TB
* more that 100 000 files

Callback mechanism
------------------
You can provide a callback URL to the plugin, this is not mandatory. An
exemple would be "http://myservice/callback".

This is used to inform another software component each time archivematica
stores something on the iRODS backend. This is not used when reading. A
typical use case would be to inform the preservation data management
software when a DIP or AIP is written.

If provided, the callback will be called using a POST request, with the
following arguments:

"name" : basename of the file or directory being written. This is the name of
the destination ("iRODS path"), and not the one on the storaage service.
For example if archivematica sends local directory /tmp/staging/foo/ to
/home/rods/AIPs/myuuid, then name will be "myuuid".

"size_in_mb": an integer providing the sum of sizes of all files contained
within the directory sent to iRODS. If only a file is sent, this is its
size. This doesn't take into account overheads from the filesystem or
blocks.

In the case of a directory, the plugin considers a list of files at the
top level of this directory, and (if present), adds a checksum field to the
POST data.
This is mainly used for 'bagit' (https://en.wikipedia.org/wiki/BagIt), which
is a commonly used format within archivematica or the preservation world.
Currently two files are considered:

"manifest-md5.txt": if present a field "checksum_manifest-md5.txt" is added
with an md5 checksum of this file, in hexadecimal representation.

"manifest-sha256.txt": if present a field "checksum_manifest-sha256.txt" is added
with an sha256 checksum of this file, in hexadecimal representation.

Copyright & Licence
-------------------
Copyright (c) 2016 Ymagis SA, http://www.ymagis.com/

Author: Thomas Capricelli <capricelli@sylphide-consulting.com>

The plugin is released under the GNU Affero General Public License, as is
archivematica-storage-service.

