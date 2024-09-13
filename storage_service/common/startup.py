import errno
import logging
import os
import pathlib
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import django.core.exceptions
from django.db import connection
from locations import models as locations_models
from locations.models.async_manager import start_async_manager

from common import utils

LOGGER = logging.getLogger(__name__)


def startup(space_path: Optional[pathlib.Path] = None) -> None:
    if space_path is None:
        space_path = pathlib.Path(os.sep)

    LOGGER.info("Running startup")

    try:
        with PopulateLock():
            populate_default_locations(space_path)
    except PopulateLockError:
        LOGGER.warning("Another worker is initializing the database.")

    start_async_manager()


class PopulateLockError(Exception):
    """MySQL lock is already held or an error occurred."""


class PopulateLock:
    """MySQL lock that gives up immediately on a held lock."""

    def __init__(self):
        self.name = "default_locations"
        self.connection = connection
        self.timeout = 0

    def __enter__(self):
        if self.connection.vendor == "mysql":
            self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.connection.vendor == "mysql":
            self.release()

    def acquire(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (self.name, self.timeout))
            result = cursor.fetchone()[0]
            if result != 1:
                raise PopulateLockError("Error obtaining the lock or already acquried.")

    def release(self):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self.name,))


def populate_default_locations(space_path: pathlib.Path) -> None:
    """Create default local filesystem space and its locations."""

    BASE_PATH = pathlib.Path("var") / "archivematica"

    try:
        space, space_created = locations_models.Space.objects.get_or_create(
            access_protocol=locations_models.Space.LOCAL_FILESYSTEM,
            path=str(space_path),
            defaults={"staging_path": space_path / BASE_PATH / "storage_service"},
        )
        if space_created:
            locations_models.LocalFilesystem.objects.create(space=space)
            LOGGER.info("Created default Space %s", space)
    except django.core.exceptions.MultipleObjectsReturned:
        LOGGER.info("Multiple default Spaces exist, done default setup.")
        return

    default_locations: List[Dict[str, Union[str, pathlib.Path, bool, None]]] = [
        {
            "purpose": locations_models.Location.TRANSFER_SOURCE,
            "relative_path": "home",
            "description": "Default transfer source",
            "default_setting": "default_transfer_source",
        },
        {
            "purpose": locations_models.Location.AIP_STORAGE,
            "relative_path": BASE_PATH / "sharedDirectory" / "www" / "AIPsStore",
            "description": "Store AIP in standard Archivematica Directory",
            "default_setting": "default_aip_storage",
        },
        {
            "purpose": locations_models.Location.DIP_STORAGE,
            "relative_path": BASE_PATH / "sharedDirectory" / "www" / "DIPsStore",
            "description": "Store DIP in standard Archivematica Directory",
            "default_setting": "default_dip_storage",
        },
        {
            "purpose": locations_models.Location.BACKLOG,
            "relative_path": BASE_PATH
            / "sharedDirectory"
            / "www"
            / "AIPsStore"
            / "transferBacklog",
            "description": "Default transfer backlog",
            "default_setting": "default_backlog",
        },
        {
            "purpose": locations_models.Location.STORAGE_SERVICE_INTERNAL,
            "relative_path": BASE_PATH / "storage_service",
            "description": "For storage service internal usage.",
            "default_setting": None,
            "create_dirs": True,
        },
        {
            "purpose": locations_models.Location.AIP_RECOVERY,
            "relative_path": BASE_PATH / "storage_service" / "recover",
            "description": "Default AIP recovery",
            "default_setting": "default_recovery",
            "create_dirs": True,
        },
    ]

    for loc_info in default_locations:
        try:
            new_loc, created = locations_models.Location.active.get_or_create(
                purpose=loc_info["purpose"],
                defaults={
                    "space": space,
                    "relative_path": loc_info["relative_path"],
                    "description": loc_info["description"],
                },
            )
            if created:
                LOGGER.info(
                    "Created default %s Location %s", loc_info["purpose"], new_loc
                )
        except locations_models.Location.MultipleObjectsReturned:
            continue

        if created and loc_info.get("create_dirs"):
            LOGGER.info("Creating %s Location %s", loc_info["purpose"], new_loc)
            try:
                new_loc_full_path = pathlib.Path(new_loc.full_path)
                new_loc_full_path.mkdir()
                # Hack for extra recovery dir
                if loc_info["purpose"] == locations_models.Location.AIP_RECOVERY:
                    (new_loc_full_path / "backup").mkdir()
            except OSError as e:
                if e.errno != errno.EEXIST:
                    LOGGER.error(
                        "%s location %s not accessible.",
                        loc_info["purpose"],
                        new_loc.full_path,
                    )

        if (
            loc_info["default_setting"]
            and utils.get_setting(loc_info["default_setting"]) is None
        ):
            utils.set_setting(loc_info["default_setting"], [str(new_loc.uuid)])
            LOGGER.info("Set %s as %s", new_loc, loc_info["default_setting"])
