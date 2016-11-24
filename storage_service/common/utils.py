import ast
import datetime
import hashlib
import logging
from lxml import etree
from lxml.builder import ElementMaker
import mimetypes
import os
import shutil
import uuid

from django.core.exceptions import ObjectDoesNotExist
from django import http

from administration import models
from storage_service import __version__

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

PREFIX_NS = {k: '{' + v + '}' for k, v in NSMAP.items()}

############ SETTINGS ############

def get_all_settings():
    """ Returns a dict of 'setting_name': value with all of the settings. """
    settings = dict(models.Settings.objects.all().values_list('name', 'value'))
    for setting, value in settings.items():
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
    related_objects = [f for f in object_._meta.get_fields() if (f.one_to_many or f.one_to_one) and f.auto_created]
    links = [rel.get_accessor_name() for rel in related_objects]
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

    # Open file in binary mode
    response = http.FileResponse(open(filepath, 'rb'))

    mimetype = mimetypes.guess_type(filename)[0]
    response['Content-type'] = mimetype
    response['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    response['Content-Length'] = os.path.getsize(filepath)

    # Delete temp dir if created
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    return response


############ XML & POINTER FILE ############

def _storage_service_agent():
    return 'Archivematica Storage Service-%s' % __version__


def mets_add_event(amdsec, event_type, event_detail='', event_outcome_detail_note=''):
    """
    Adds a PREMIS:EVENT and associated PREMIS:AGENT to the provided amdSec.
    """
    # Add PREMIS:EVENT
    digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
    event = mets_event(
        digiprov_id=digiprov_id,
        event_type=event_type,
        event_detail=event_detail,
        event_outcome_detail_note=event_outcome_detail_note,
    )
    LOGGER.debug('PREMIS:EVENT %s: %s', event_type, etree.tostring(event, pretty_print=True))
    amdsec.append(event)

    # Add PREMIS:AGENT for storage service
    digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
    digiprov_agent = mets_ss_agent(amdsec, digiprov_id)
    if digiprov_agent is not None:
        LOGGER.debug('PREMIS:AGENT SS: %s', etree.tostring(digiprov_agent, pretty_print=True))
        amdsec.append(digiprov_agent)


def mets_event(digiprov_id, event_type, event_detail='', event_outcome_detail_note='', agent_type='storage service', agent_value=None):
    """
    Create and return a PREMIS:EVENT.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if agent_value is None:
        agent_value = _storage_service_agent()
    # New E with namespace for PREMIS
    EP = ElementMaker(
        namespace=NSMAP['premis'],
        nsmap={'premis': NSMAP['premis']})
    EM = ElementMaker(
        namespace=NSMAP['mets'],
        nsmap={'mets': NSMAP['mets']})
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
    digiprov_event = EM.digiprovMD(
        EM.mdWrap(
            EM.xmlData(premis_event),
            MDTYPE="PREMIS:EVENT",
        ),
        ID=digiprov_id,
    )
    return digiprov_event


def mets_ss_agent(xml, digiprov_id, agent_value=None, agent_type='storage service'):
    """
    Create and return a PREMIS:AGENT for the SS, if not found in `xml`.
    """
    if agent_value is None:
        agent_value = _storage_service_agent()
    existing_agent = xml.xpath(".//mets:agentIdentifier[mets:agentIdentifierType='{}' and mets:agentIdentifierValue='{}']".format(agent_type, agent_value), namespaces=NSMAP)
    if existing_agent:
        return None
    EP = ElementMaker(
        namespace=NSMAP['premis'],
        nsmap={'premis': NSMAP['premis']})
    EM = ElementMaker(
        namespace=NSMAP['mets'],
        nsmap={'mets': NSMAP['mets']})
    digiprov_agent = EM.digiprovMD(
        EM.mdWrap(
            EM.xmlData(
                EP.agent(
                    EP.agentIdentifier(
                        EP.agentIdentifierType(agent_type),
                        EP.agentIdentifierValue(agent_value),
                    ),
                    EP.agentName('Archivematica Storage Service'),
                    EP.agentType('software'),
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
