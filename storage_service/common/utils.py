import ast
import datetime
import hashlib
import logging
from lxml import etree
from lxml.builder import E, ElementMaker
import mimetypes
import os
import shutil
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django.core.servers.basehttp import FileWrapper
from django import http

from administration import models
from common import version

LOGGER = logging.getLogger(__name__)

NSMAP = {
    'atom': 'http://www.w3.org/2005/Atom',  # Atom Syndication Format
    'app': 'http://www.w3.org/2007/app',  # Atom Publishing Protocol
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'lom': 'http://lockssomatic.info/SWORD2',
    'mets': 'http://www.loc.gov/METS/',
    'premis': 'info:lc/xmlns/premis-v2',
    'sword': 'http://purl.org/net/sword/terms/',
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
        return http.HttpResponseNotFound("File not found")

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


############ XML & POINTER FILE ############

def _storage_service_agent():
    return 'Archivematica Storage Service-%s' % version.get_version()


def mets_add_event(digiprov_id, event_type, event_detail='', event_outcome_detail_note='', agent_type='storage service', agent_value=None):
    """
    Create and return a PREMIS:EVENT.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if agent_value == None:
        agent_value = _storage_service_agent()
    # New E with namespace for PREMIS
    EP = ElementMaker(
        namespace=NSMAP['premis'],
        nsmap={None: NSMAP['premis']})
    premis_event = EP.event(
        EP.eventIdentifier(
            EP.eventIdentifierType('UUID'),
            EP.eventIdentifierValue(str(uuid.uuid4()))
        ),
        EP.eventType(event_type),
        EP.eventDateTime(now),
        EP.eventDetail(event_detail),
        EP.eventOutcomeInformation(
            EP.eventOutcome(),
            EP.eventOutcomeDetail(
                EP.eventOutcomeDetailNote(event_outcome_detail_note)
            )
        ),
        EP.linkingAgentIdentifier(
            EP.linkingAgentIdentifierType(agent_type),
            EP.linkingAgentIdentifierValue(agent_value),
        ),
        version='2.2'
    )
    premis_event.set('{'+NSMAP['xsi']+'}schemaLocation', 'info:lc/xmlns/premis-v2 http://www.loc.gov/standards/premis/v2/premis-v2-2.xsd')

    # digiprovMD to wrap PREMIS event
    digiprov_event = E.digiprovMD(
        E.mdWrap(
            E.xmlData(premis_event),
            MDTYPE="PREMIS:EVENT",
        ),
        ID=digiprov_id,
    )
    return digiprov_event


def mets_ss_agent(xml, digiprov_id, agent_value=None, agent_type='storage service'):
    """
    Create and return a PREMIS:AGENT for the SS, if not found in `xml`.
    """
    if agent_value == None:
        agent_value = _storage_service_agent()
    existing_agent = xml.xpath(".//mets:agentIdentifier[mets:agentIdentifierType='{}' and mets:agentIdentifierValue='{}']".format(agent_type, agent_value), namespaces=NSMAP)
    if existing_agent:
        return None
    digiprov_agent = E.digiprovMD(
        E.mdWrap(
            E.xmlData(
                E.agent(
                    E.agentIdentifier(
                        E.agentIdentifierType(agent_type),
                        E.agentIdentifierValue(agent_value),
                    ),
                    E.agentName('Archivematica Storage Service'),
                    E.agentType('software'),
                )
            ),
            MDTYPE='PREMIS:AGENT',
        ),
        ID=digiprov_id,
    )
    return digiprov_agent


############ OTHER ############

def generate_checksum(file_path, checksum_type='md5'):
    """
    Returns checksum object for `file_path` using `checksum_type`.

    If checksum_type is not a valid checksum, ValueError raised by hashlib.
    """
    checksum = hashlib.new(checksum_type)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(128*checksum.block_size), b''):
            checksum.update(chunk)
    return checksum


def uuid_to_path(uuid):
    """ Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name. """
    uuid = uuid.replace("-", "")
    path = [uuid[i:i+4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    LOGGER.debug("path %s", path)
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

def coerce_str(string):
    """ Return string as a str, not a unicode, encoded in utf-8.

    :param basestring string: String to convert
    :return: string converted to str, encoded in utf-8 if needed.
    """
    if isinstance(string, unicode):
        return string.encode('utf-8')
    return string
