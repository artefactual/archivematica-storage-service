# Note that while the signals are not actually used here,
# they should be imported here to make sure that they
# are imported very early on globally. This ensures that
# the signals themselves are registered early.
from .. import signals

# Required by other files
class StorageException(Exception):
    """ Exceptions specific to the service."""
    pass

# Common
# May have multiple models, so import * and use __all__ in file.
from event import *
from location import *
from package import *
from pipeline import *
from space import *
# not importing managers as that is internal

# Protocol Spaces
# Will only have one model, so import that directly
from duracloud import Duracloud
from fedora import Fedora, PackageDownloadTask, PackageDownloadTaskFile
from local_filesystem import LocalFilesystem
from lockssomatic import Lockssomatic
from nfs import NFS
from pipeline_local import PipelineLocalFS