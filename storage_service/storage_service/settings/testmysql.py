# flake8: noqa

from __future__ import absolute_import

import dj_database_url

from .test import *

DATABASES["default"] = dj_database_url.parse(
    "mysql://archivematica:demo@mysql/SSTEST", conn_max_age=600
)
