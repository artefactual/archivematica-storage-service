# stdlib, alphabetical
import os
import subprocess
import tempfile
import urllib2

# Core Django, alphabetical
from django.core.exceptions import ObjectDoesNotExist

# This project, alphabetical
from locations.models import Deposit
from locations.models import Location

def deposit_storage_path(uuid):
    try:
        deposit = Deposit.objects.get(uuid=uuid)
        return deposit.full_path()
    except ObjectDoesNotExist:
        return None

def deposit_location_path(location_uuid):
    location = Location.objects.get(uuid=location_uuid)
    return location.full_path()

def deposit_list(location_uuid):
    location = Location.objects.get(uuid=location_uuid)

    deposit_list = []
    deposits = Deposit.objects.filter(location=location)
    for deposit in deposits:
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
