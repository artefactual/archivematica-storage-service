"""Import AIP Django management command: imports an AIP into the Storage
Service.

The user must minimally provide the full path to a locally available AIP via
the ``--aip-path`` argument. The user may also specify the AIP Storage location
UUID indicating where the AIP should be stored (using
``--aip-storage-location``) as well as the UUID of the pipeline that the AIP
was created with (using ``--pipeline``).

The command will:

- validate the AIP (make sure it is a valid Bag),
- decompress the AIP (if told to do so),
- copy the AIP to a local filesystem AIP Storage location,
- compress the AIP (if told to do so),
- create a database row (in the locations_package table) for the AIP in the
  Storage Service database, and
- call the AIP model instance's ``store_aip`` method, thereby moving the AIP to
  its ultimate destination space/location (as specified by the caller) and
  creating a pointer file (if needed).

Here is an example of running this command in an am.git Docker Compose deploy
to import an uncompressed AIP new_uncompressed.tar.gz ::

    $ make manage-ss ARG='import_aip /home/archivematica/new_uncompressed.tar.gz --decompress-source --compression-algorithm="7z with bzip"'

Note that in the above command we are importing a .tar.gz file that---once
uncompressed---is expected to be an uncompressed AIP. That's what the
``--decompress-source`` flag means. The ``--compression-algorithm`` option
indicates which compression algorithm to use for the final, compressed AIP. The
final AIP in this case will be compressed and will have a pointer file.

To get help::

    $ make manage-ss ARG='import_aip -h'

Question: Why are the permissions 664 on an imported AIP but 775 on one created
via a pipeline? Should this be fixed by the import command?::

    $ ls -lh /tmp/am-pipeline-data/www/AIPsStore/0fde/dcc1/599d/4f6e/b132/4b7b/c035/5b1f/CVA1426-0fdedcc1-599d-4f6e-b132-4b7bc0355b1f.7z
    -rw-rw-r--  1 joeldunham  wheel    25M 30 Jul 23:03 /tmp/am-pipeline-data/www/AIPsStore/0fde/dcc1/599d/4f6e/b132/4b7b/c035/5b1f/CVA1426-0fdedcc1-599d-4f6e-b132-4b7bc0355b1f.7z
    $ ls -lh /tmp/am-pipeline-data/www/AIPsStore/237e/12b4/03c9/451a/9be7/4915/b0bd/9012/FakeCVA2-237e12b4-03c9-451a-9be7-4915b0bd9012.7z
    -rwxrwxr-x  1 joeldunham  wheel    51M 30 Jul 22:58 /tmp/am-pipeline-data/www/AIPsStore/237e/12b4/03c9/451a/9be7/4915/b0bd/9012/FakeCVA2-237e12b4-03c9-451a-9be7-4915b0bd9012.7z

"""


import glob
import logging
import os
from pwd import getpwnam
import shlex
import shutil
import subprocess
import tarfile
import tempfile

import bagit
import scandir
from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError

from administration.models import Settings
from common import premis, utils
from locations import models


# Suppress the logging from models/package.py
logging.config.dictConfig({"version": 1, "disable_existing_loggers": True})


DEFAULT_AS_LOCATION = "default_AS_location"
DEFAULT_UNIX_OWNER = "archivematica"
ANSI_HEADER = "\033[95m"
ANSI_OKGREEN = "\033[92m"
ANSI_WARNING = "\033[93m"
ANSI_FAIL = "\033[91m"
ANSI_ENDC = "\033[0m"


class Command(BaseCommand):

    help = "Import an AIP into the Storage Service"

    def add_arguments(self, parser):
        parser.add_argument("aip_path", help="Full path to the AIP to be imported")
        parser.add_argument(
            "--aip-storage-location",
            help="UUID of the AIP Storage Location where the imported AIP"
            " should be stored. Defaults to default AS location.",
            default=DEFAULT_AS_LOCATION,
            required=False,
        )
        parser.add_argument(
            "--pipeline",
            help="UUID of a pipeline that should be listed as the AIP's"
            " origin. Defaults to an arbitrary pipeline.",
            required=False,
        )
        parser.add_argument(
            "--decompress-source",
            help="Use this flag to indicate that AIP_PATH should be"
            " decompressed and the resulting DIRECTORY should be the"
            " UNCOMPRESSED AIP to be imported.",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--compression-algorithm",
            help="The compression algorithm to use when compressing the"
            " imported AIP. Omit this if the AIP is already compressed or"
            " if you want to import an uncompressed AIP as is.",
            choices=utils.COMPRESSION_ALGORITHMS,
            default=None,
        )
        parser.add_argument(
            "--unix-owner",
            help="The Unix system user that should own the file(s) of the"
            " imported AIP. Default: {}".format(DEFAULT_UNIX_OWNER),
            default=DEFAULT_UNIX_OWNER,
        )
        parser.add_argument(
            "--force",
            help="Do not check if AIP uuid already exists in the Storage"
            " Service. If so, will overwrite the existing AIP without prompt.",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--tmp-dir",
            help="Temporary directory for processing, passed as dir parameter"
            " to tempfile.mkdtemp(), e.g,'/var/archivematica/sharedDirectory/tmp'."
            " Default: None ",
            default=None,
            required=False,
        )

    def handle(self, *args, **options):
        print(header("Attempting to import the AIP at {}.".format(options["aip_path"])))
        try:
            import_aip(
                options["aip_path"],
                options["aip_storage_location"],
                options["decompress_source"],
                options["compression_algorithm"],
                options["pipeline"],
                options["unix_owner"],
                options["force"],
                options["tmp_dir"],
            )
        except ImportAIPException as err:
            print(fail(err))


class ImportAIPException(Exception):
    """An error occurred when attempting to import an AIP."""


def ansi_format(start_sym, string):
    return f"{start_sym}{string}{ANSI_ENDC}"


def header(string):
    return ansi_format(ANSI_HEADER, string)


def okgreen(string):
    return ansi_format(ANSI_OKGREEN, string)


def warning(string):
    return ansi_format(ANSI_WARNING, string)


def fail(string):
    return ansi_format(ANSI_FAIL, string)


def is_compressed(aip_path):
    return os.path.isfile(aip_path)


def tree(path):
    for root, _, files in scandir.walk(path):
        level = root.replace(path, "").count(os.sep)
        indent = " " * 4 * (level)
        print(header(f"{indent}{os.path.basename(root)}/"))
        subindent = " " * 4 * (level + 1)
        for f in files:
            print(okgreen(f"{subindent}{f}"))


def decompress(aip_path, decompress_source, temp_dir):
    if decompress_source and is_compressed(aip_path):
        return _decompress(aip_path, temp_dir)
    return aip_path


def _decompress(aip_path, temp_dir):
    is_tar_gz = aip_path.endswith(".tar.gz")
    is_7z = aip_path.endswith(".7z")
    if not (is_tar_gz or is_7z):
        raise ImportAIPException(f"Unable to decompress the AIP at {aip_path}")
    if is_tar_gz:
        return _decompress_tar_gz(aip_path, temp_dir)
    if is_7z:
        return _decompress_7z(aip_path, temp_dir)


def _decompress_tar_gz(aip_path, temp_dir):
    with tarfile.open(aip_path) as tar:
        aip_root_dir = os.path.commonprefix(tar.getnames())
        tar.extractall(path=temp_dir)
    return os.path.join(temp_dir, aip_root_dir)


def _decompress_7z(aip_path, temp_dir):
    cmd = shlex.split(f"7z x {aip_path} -o{temp_dir}")
    subprocess.check_output(cmd)
    return os.path.join(temp_dir, os.listdir(temp_dir)[0])


def confirm_aip_exists(aip_path):
    if not os.path.exists(aip_path):
        raise ImportAIPException(f"There is nothing at {aip_path}")


def validate(aip_path):
    error_msg = f"The AIP at {aip_path} is not a valid Bag; aborting."
    try:
        bag = bagit.Bag(aip_path)
    except bagit.BagError:
        if is_compressed(aip_path):
            error_msg = f"{error_msg} Try passing the --decompress-source flag."
        raise ImportAIPException(error_msg)
    else:
        if not bag.is_valid():
            raise ImportAIPException(error_msg)


def get_aip_mets_path(aip_path):
    aip_mets_path = glob.glob(os.path.join(aip_path, "data", "METS*xml"))
    if not aip_mets_path:
        raise ImportAIPException(f"Unable to find a METS file in {aip_path}.")
    return aip_mets_path[0]


def get_aip_uuid(aip_mets_path):
    return os.path.basename(aip_mets_path)[5:41]


def get_aip_storage_locations(aip_storage_location_uuid):
    """Return a 2-tuple of AIP Storage (AS) locations:

    - local_as_location: a LocalFilesystem (FS) location
    - final_as_location: a final (destination) location, which may be of any
      protocol.

    The point is that we must first manually move the AIP into the local
    filesystem-type location, and then make an API request to the Storage
    Service to move the AIP to the final destination location. Note: if the
    user specifies (via ``aip_storage_location_uuid``) an FS-type location, then
    we just return a 2-tuple where both elements are that same location.
    """
    if aip_storage_location_uuid == DEFAULT_AS_LOCATION:
        aip_storage_location_uuid = Settings.objects.get(
            name=aip_storage_location_uuid
        ).value
    try:
        final_as_location = models.Location.objects.get(uuid=aip_storage_location_uuid)
    except models.Location.DoesNotExist:
        raise ImportAIPException(
            "Unable to find an AIP storage location matching {}.".format(
                aip_storage_location_uuid
            )
        )
    else:
        if final_as_location.space.access_protocol != models.Space.LOCAL_FILESYSTEM:
            local_as_location = models.Location.objects.filter(
                space__access_protocol=models.Space.LOCAL_FILESYSTEM
            ).first()
            return local_as_location, final_as_location
        return final_as_location, final_as_location


def fix_ownership(aip_path, unix_owner):
    """Set ``unix_owner`` as the user and group of all files and directories in
    ``aip_path``.
    """
    passwd_struct = getpwnam(unix_owner)
    am_uid = passwd_struct.pw_uid
    am_gid = passwd_struct.pw_gid
    for root, dirs, files in scandir.walk(aip_path):
        os.chown(root, am_uid, am_gid)
        for dir_ in dirs:
            os.chown(os.path.join(root, dir_), am_uid, am_gid)
        for file_ in files:
            os.chown(os.path.join(root, file_), am_uid, am_uid)


def copy_aip_to_aip_storage_location(
    aip_model_inst, aip_path, local_as_location, unix_owner
):
    aip_storage_location_path = local_as_location.full_path
    dest = os.path.join(aip_storage_location_path, aip_model_inst.current_path)
    copy_rsync(aip_path, dest)
    fix_ownership(dest, unix_owner)
    print(
        okgreen(
            "Location: {} ({}).".format(
                local_as_location.uuid, local_as_location.space.access_protocol
            )
        )
    )


def copy_rsync(source, destination):
    source = os.path.join(source, "")
    p = subprocess.Popen(
        [
            "rsync",
            "-t",
            "-O",
            "--protect-args",
            "--chmod=ugo+rw",
            "-r",
            source,
            destination,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    p.communicate()
    if p.returncode != 0:
        raise ImportAIPException(
            f"Unable to move the AIP from {source} to {destination}."
        )


def get_pipeline(adoptive_pipeline_uuid):
    if adoptive_pipeline_uuid:
        try:
            return models.Pipeline.objects.get(uuid=adoptive_pipeline_uuid)
        except models.Pipeline.DoesNotExist:
            raise ImportAIPException(
                f"There is no pipeline with uuid {adoptive_pipeline_uuid}"
            )
    ret = models.Pipeline.objects.first()
    print(okgreen(f"Pipeline: {ret.uuid}"))
    return ret


def save_aip_model_instance(aip_model_inst):
    try:
        aip_model_inst.save()
    except IntegrityError:
        models.Package.objects.filter(uuid=aip_model_inst.uuid).delete()
        aip_model_inst.save()


def check_if_aip_already_exists(aip_uuid):
    duplicates = models.Package.objects.filter(uuid=aip_uuid).all()
    if duplicates:
        prompt = warning(
            "An AIP with UUID {} already exists in this Storage Service? If you"
            " want to import this AIP anyway (and destroy the existing one),"
            ' then enter "y" or "yes": '.format(aip_uuid)
        )
        user_response = input(prompt)
        if user_response.lower() not in ("y", "yes"):
            raise ImportAIPException("Aborting importation of an already existing AIP")


def compress(aip_model_inst, compression_algorithm):
    """Use the Package model's compress_package method to compress the AIP
    being imported, update the Package model's ``size`` attribute, retrieve
    PREMIS agents and event for the compression (using the package model's
    ``create_premis_aip_compression_event`` method) and return a 3-tuple:
    (aip_model_inst, compression_event, compression_agents).
    """
    if not compression_algorithm:
        return
    (
        compressed_aip_path,
        compressed_aip_parent_path,
        details,
    ) = aip_model_inst.compress_package(compression_algorithm, detailed_output=True)
    compressed_aip_fname = os.path.basename(compressed_aip_path)
    aip_current_dir = os.path.dirname(aip_model_inst.current_path)
    shutil.rmtree(aip_model_inst.full_path)
    new_current_path = os.path.join(aip_current_dir, compressed_aip_fname)
    new_full_path = os.path.join(
        aip_model_inst.current_location.full_path, new_current_path
    )
    shutil.move(compressed_aip_path, new_full_path)
    aip_model_inst.current_path = new_current_path
    shutil.rmtree(compressed_aip_parent_path)
    aip_model_inst.size = utils.recalculate_size(new_full_path)
    compression_agents = [premis.SS_AGENT]
    compression_event = premis.create_premis_aip_compression_event(
        details["event_detail"],
        details["event_outcome_detail_note"],
        agents=compression_agents,
    )
    return aip_model_inst, compression_event, compression_agents


def import_aip(
    aip_path,
    aip_storage_location_uuid,
    decompress_source,
    compression_algorithm,
    adoptive_pipeline_uuid,
    unix_owner,
    force,
    tmp_dir,
):
    confirm_aip_exists(aip_path)
    temp_dir = tempfile.mkdtemp(dir=tmp_dir)
    aip_path = decompress(aip_path, decompress_source, temp_dir)
    validate(aip_path)
    aip_mets_path = get_aip_mets_path(aip_path)
    aip_uuid = get_aip_uuid(aip_mets_path)
    if not force:
        check_if_aip_already_exists(aip_uuid)
    local_as_location, final_as_location = get_aip_storage_locations(
        aip_storage_location_uuid
    )
    aip_model_inst = models.Package(
        uuid=aip_uuid,
        package_type="AIP",
        status="UPLOADED",
        size=utils.recalculate_size(aip_path),
        origin_pipeline=get_pipeline(adoptive_pipeline_uuid),
        current_location=local_as_location,
        current_path=os.path.basename(os.path.normpath(aip_path)),
    )
    copy_aip_to_aip_storage_location(
        aip_model_inst, aip_path, local_as_location, unix_owner
    )
    premis_events = premis_agents = None
    if compression_algorithm:
        aip_model_inst, compression_event, premis_agents = compress(
            aip_model_inst, compression_algorithm
        )
        premis_events = [compression_event]
    aip_model_inst.current_location = final_as_location
    save_aip_model_instance(aip_model_inst)
    aip_model_inst.store_aip(
        origin_location=local_as_location,
        origin_path=aip_model_inst.current_path,
        premis_events=premis_events,
        premis_agents=premis_agents,
    )
    shutil.rmtree(temp_dir)

    print(
        okgreen(
            "Path: {}.".format(
                os.path.join(
                    aip_model_inst.current_location.full_path,
                    aip_model_inst.current_path,
                )
            )
        )
    )
    print(okgreen(f"Successfully imported AIP {aip_uuid}."))
