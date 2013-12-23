import ast
import logging
import mimetypes
import os
import shutil


from django.core.exceptions import ObjectDoesNotExist
from django.core.servers.basehttp import FileWrapper
from django import http

from administration import models

logger = logging.getLogger(__name__)

NSMAP = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'mets': 'http://www.loc.gov/METS/',
    'premis': 'info:lc/xmlns/premis-v2',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}

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
        try:
            linked_objects = getattr(object_, link).all()
        except (AttributeError, ObjectDoesNotExist):
            # This is probably a OneToOneField, and should be handled differently
            # Or the relation has no entries
            continue
        for linked_object in linked_objects:
            dependent_objects.append(
                {'model': linked_object._meta.verbose_name,
                 'value': linked_object})
    return dependent_objects


############ DOWNLOADING ############

def download_file_stream(filepath, temp_dir=None):
    """
    Returns `filepath` as a HttpResponse stream.

    Deletes temp_dir once stream created if it exists.
    """
    # If not found, return 404
    if not os.path.exists(filepath):
        return http.HttpNotFound("File not found")

    filename = os.path.basename(filepath)
    extension = os.path.splitext(filepath)[1].lower()

    wrapper = FileWrapper(file(filepath))
    response = http.HttpResponse(wrapper)

    # force download for certain filetypes
    extensions_to_download = ['.7z', '.zip']
    if extension in extensions_to_download:
        response['Content-Type'] = 'application/force-download'
        response['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    else:
        mimetype = mimetypes.guess_type(filename)[0]
        response['Content-type'] = mimetype

    response['Content-Length'] = os.path.getsize(filepath)

    # Delete temp dir if created
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    return response

############ OTHER ############

def uuid_to_path(uuid):
    """ Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name. """
    uuid = uuid.replace("-", "")
    path = [uuid[i:i+4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    logging.debug("path {}".format(path))
    return path

def removedirs(relative_path, base=None):
    """ Removes leaf directory of relative_path and all empty directories in
    relative_path, but nothing from base.

    Cribbed from the implementation of os.removedirs. """
    if not base:
        return os.removedirs(relative_path)
    try:
        os.rmdir(os.path.join(base, relative_path))
    except os.error:
        pass
    head, tail = os.path.split(relative_path)
    if not tail:
        head, tail = os.path.split(head)
    while head and tail:
        try:
            os.rmdir(os.path.join(base, head))
        except os.error:
            break
        head, tail = os.path.split(head)
