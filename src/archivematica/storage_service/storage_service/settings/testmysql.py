import dj_database_url

from archivematica.storage_service.storage_service.settings.test import *

DATABASES["default"] = dj_database_url.parse(
    "mysql://archivematica:demo@mysql/SSTEST", conn_max_age=600
)
DATABASES["default"]["TEST"] = {"NAME": "test_SSTEST"}
