# stdlib, alphabetical
import os
import subprocess
import tempfile
import urllib2

# Core Django, alphabetical
from django.core.exceptions import ObjectDoesNotExist

# External dependencies, alphabetical
from annoying.functions import get_object_or_None

# This project, alphabetical
from locations.models import Location
from locations.models import Space

def get_deposit(uuid):
    return get_object_or_None(Location, uuid=uuid)

def deposit_list(space_uuid):
    space = Space.objects.get(uuid=space_uuid)

    deposit_list = []
    # TODO: add purpose spec to filter
    deposits = Location.objects.filter(space=space)
    for deposit in deposits:
        if deposit.purpose == Location.SWORD_DEPOSIT:
            deposit_list.append(deposit.uuid)
    return deposit_list

def write_file_from_request_body(request, file_path):
    bytes_written = 0
    new_file = open(file_path, 'ab')
    chunk = request.read()
    if chunk != None:
        new_file.write(chunk)
        bytes_written += len(chunk)
        chunk = request.read()
    new_file.close()
    return bytes_written

def get_file_md5_checksum(filepath):
    raw_result = subprocess.Popen(["md5sum", filepath],stdout=subprocess.PIPE).communicate()[0]
    return raw_result[0:32]

def parse_filename_from_content_disposition(header):
    filename = header.split('filename=')[1]
    if filename[0] == '"' or filename[0] == "'":
        filename = filename[1:-1]
    return filename

def write_request_body_to_temp_file(request):
    filehandle, temp_filepath = tempfile.mkstemp()
    write_file_from_request_body(request, temp_filepath)
    return temp_filepath

# recursive
def pad_destination_filepath_if_it_already_exists(filepath, original=None, attempt=0):
    if original == None:
        original = filepath
    attempt = attempt + 1
    if os.path.exists(filepath):
        return pad_destination_filepath_if_it_already_exists(original + '_' + str(attempt), original, attempt)
    return filepath

def download_resource(url, destination_path):
    response = urllib2.urlopen(url)
    filename = _filename_from_response(response)

    if filename == None:
        filename = os.path.basename(url)

    filepath = os.path.join(destination_path, filename)
    buffer = 16 * 1024
    with open(filepath, 'wb') as fp:
        while True:
            chunk = response.read(buffer)
            if not chunk: break
            fp.write(chunk)
    return filename

def _filename_from_response(response):
    info = response.info()
    if 'content-disposition' in info:
        return parse_filename_from_content_disposition(info['content-disposition'])
    else:
        return None
