import logging
import os.path

logger = logging.getLogger(__name__)


def uuid_to_path(uuid):
    """ Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name. """
    uuid = uuid.replace("-","")
    path = [uuid[i:i+4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    logging.debug("path {}".format(path))
    return path
