import logging
import os.path

from administration import models

logger = logging.getLogger(__name__)


def get_setting(setting, default=None):
    """ Returns the value of 'setting' from models.Settings, 'default' if not found."""
    try:
        setting = models.Settings.objects.get(name=setting)
        if setting.value == "False":
            return False
        else:
            return_value = setting.value
    except:
        return_value = default
    return return_value

def set_setting(setting, value=None):
    """ Sets 'setting' to 'value' in models.Settings. """
    try:
        setting_data = models.Settings.objects.get(name=setting)
    except:
        setting_data = models.Settings.objects.create()
        setting_data.name = setting
    setting_data.value = value
    setting_data.save()


def uuid_to_path(uuid):
    """ Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name. """
    uuid = uuid.replace("-", "")
    path = [uuid[i:i+4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    logging.debug("path {}".format(path))
    return path
