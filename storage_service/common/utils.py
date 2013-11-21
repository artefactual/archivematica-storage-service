import ast
import logging
import os.path

from administration import models

logger = logging.getLogger(__name__)

############ SETTINGS ############

def get_all_settings():
    """ Returns a dict of 'setting_name': value with all of the settings. """
    settings = dict(models.Settings.objects.all().values_list('name', 'value'))
    for setting, value in settings.iteritems():
        settings[setting] = ast.literal_eval(value)
    return settings

def get_setting(setting, default=None):
    """ Returns the value of 'setting' from models.Settings, 'default' if not found."""
    try:
        setting = models.Settings.objects.get(name=setting)
    except:
        return_value = default
    else:
        return_value = ast.literal_eval(setting.value)
    return return_value

def set_setting(setting, value=None):
    """ Sets 'setting' to 'value' in models.Settings.

    'value' must be an object that can be recreated by calling literal_eval on
    its string representation.  Strings are automatically esacped. """
    # Since we call literal_eval on settings when we extract them, we need to
    # put quotes around strings so they remain strings
    if isinstance(value, basestring):
        value = "'{}'".format(value)
    setting, _ = models.Settings.objects.get_or_create(name=setting)
    setting.value = value
    setting.save()

############ DEPENDENCIES ############

def dependent_objects(object_):
    """ Returns all the objects that rely on 'object_'. """
    links = [rel.get_accessor_name() for rel in object_._meta.get_all_related_objects()]
    dependent_objects = []
    for link in links:
        linked_objects = getattr(object_, link).all()
        for linked_object in linked_objects:
            dependent_objects.append(
                {'model': linked_object._meta.verbose_name,
                 'value': linked_object})
    return dependent_objects

############ OTHER ############

def uuid_to_path(uuid):
    """ Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name. """
    uuid = uuid.replace("-", "")
    path = [uuid[i:i+4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    logging.debug("path {}".format(path))
    return path
