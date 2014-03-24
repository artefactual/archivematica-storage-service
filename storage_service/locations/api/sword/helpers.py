# stdlib, alphabetical
import base64
import json
import logging
import os
from multiprocessing import Process
import shutil
import subprocess
import tempfile
import time
import urllib
import urllib2

# Core Django, alphabetical
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

# External dependencies, alphabetical
from annoying.functions import get_object_or_None

# This project, alphabetical
from locations.models import Location
from locations.models import LocationDownloadTask
from locations.models import LocationDownloadTaskFile
from locations.models import Space
from locations.models import SwordServer

LOGGER = logging.getLogger(__name__)
logging.basicConfig(filename="/tmp/storage_service.log",
    level=logging.INFO)

"""
Shortcut to retrieve deposit data

Returns deposit model object or None
"""
def get_deposit(uuid):
    return get_object_or_None(Location, uuid=uuid)

"""
Retrieve list of deposits
TODO: filter out completed ones?

Returns list containing deposit UUIDs
"""
def deposit_list(space_uuid):
    space = Space.objects.get(uuid=space_uuid)

    deposit_list = []
    deposits = Location.objects.filter(space=space)
    for deposit in deposits:
        if deposit.purpose == Location.SWORD_DEPOSIT:
            deposit_list.append(deposit.uuid)
    return deposit_list

"""
Write HTTP request's body content to a file

Return the number of bytes successfully written
"""
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

"""
Write HTTP request's body content to a temp file

Return the temp file's path
"""
def write_request_body_to_temp_file(request):
    filehandle, temp_filepath = tempfile.mkstemp()
    write_file_from_request_body(request, temp_filepath)
    return temp_filepath

"""
Get the MD5 checksum for a file

Return MD5 checksum
"""
def get_file_md5_checksum(filepath):
    raw_result = subprocess.Popen(["md5sum", filepath],stdout=subprocess.PIPE).communicate()[0]
    return raw_result[0:32]

"""
Parse a filename from HTTP Content-Disposition data

Return filename
"""
def parse_filename_from_content_disposition(header):
    filename = header.split('filename=')[1]
    if filename[0] == '"' or filename[0] == "'":
        filename = filename[1:-1]
    return filename

"""
Pad a filename numerically, preserving the file extension, if it's a duplicate
of an existing file. This function is recursive.

Returns padded (if necessary) file path
"""
def pad_destination_filepath_if_it_already_exists(filepath, original=None, attempt=0):
    if original == None:
        original = filepath
    attempt = attempt + 1
    if os.path.exists(filepath):
        return pad_destination_filepath_if_it_already_exists(original + '_' + str(attempt), original, attempt)
    return filepath

"""
Download a URL resource to a destination directory, using the response's
Content-Disposition header, if available, to determine the destination
filename (using the filename at the end of the URL otherwise)

Returns filename of downloaded resource
"""
def download_resource(url, destination_path, filename=None):
    logging.info('downloading url: ' + url)
    request = urllib2.Request(url)
    base64string = base64.encodestring('%s:%s' % ('fedoraAdmin', 'islandora')).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)   
    response = urllib2.urlopen(request)
    info = response.info()
    if filename == None:
        if 'content-disposition' in info:
            filename = parse_filename_from_content_disposition(info['content-disposition'])
        else:
            filename = os.path.basename(url)
    logging.info('Filename set to ' + filename)

    filepath = os.path.join(destination_path, filename)
    buffer_size = 16 * 1024
    with open(filepath, 'wb') as fp:
        while True:
            chunk = response.read(buffer_size)
            if not chunk: break
            fp.write(chunk)
    return filename

"""
Return a deposit's download tasks.
"""
def deposit_download_tasks(deposit_uuid):
    deposit = get_deposit(deposit_uuid)
    return LocationDownloadTask.objects.filter(location=deposit)

"""
Return deposit status, indicating whether any incomplete or failed batch
downloads exist.
"""
def deposit_downloading_status(deposit_uuid):
    tasks = deposit_download_tasks(deposit_uuid)
    if len(tasks) > 0:
        # check each task for completion and failure
        complete = True
        failed = False

        for task in tasks:
            if task.downloading_status() != 'complete':
                complete = False
                if task.downloading_status() == 'failed':
                    failed = True
        if failed:
            return 'failed'
        else:
            if complete:
                return 'complete'
            else:
                return 'incomplete'
    else:
        return 'complete'

"""
Spawn an asynchrnous batch download
"""
def spawn_download_task(deposit_uuid, objects):
    p = Process(target=_fetch_content, args=(deposit_uuid, objects))
    p.start()

"""
Download a number of files, keeping track of progress and success using a
database record. After downloading, finalize deposit if requested.
"""
def _fetch_content(deposit_uuid, objects):
    # add download task to keep track of progress
    deposit = get_deposit(deposit_uuid)
    task = LocationDownloadTask(location=deposit)
    task.downloads_attempted = len(objects)
    task.downloads_completed = 0
    task.save()

    # download the files
    temp_dir = tempfile.mkdtemp()

    completed = 0
    for item in objects:
        # create download task file record
        task_file = LocationDownloadTaskFile(task=task)
        task_file.save()

        try:
            filename = item['filename']

            task_file.filename = filename
            task_file.url = item['url']
            task_file.save()

            download_resource(item['url'], temp_dir, filename)
            shutil.move(os.path.join(temp_dir, filename),
                os.path.join(deposit.full_path(), filename))

            # mark download task file record complete or failed
            task_file.completed = True
            task_file.save()

            logging.info('Saved file to ' + os.path.join(deposit.full_path(), filename))
            completed += 1
        except:
            # an error occurred
            task_file.failed = True
            task_file.save()

    # remove temp dir
    shutil.rmtree(temp_dir)

    # record the number of successful downloads and completion time
    task.downloads_completed = completed
    task.download_completion_time = timezone.now()
    task.save()

    # if the deposit is ready for finalization and this is the last batch
    # download to complete, then finalize
    if deposit.ready_for_finalization and deposit_downloading_status(deposit_uuid) == 'complete':
        _finalize_if_not_empty(deposit_uuid)

"""
Spawn an asynchronous finalization
"""
def spawn_finalization(deposit_uuid):
    p = Process(target=_finalize_if_not_empty, args=(deposit_uuid, ))
    p.start()

"""
Approve a deposit for processing and mark is as completed or finalization failed

Returns True if completed successfully, False if not
"""
def _finalize_if_not_empty(deposit_uuid):
    deposit = get_deposit(deposit_uuid)
    completed = False
    
    # don't finalize if still downloading
    if deposit_downloading_status(deposit_uuid) == 'complete':
        if len(os.listdir(deposit.full_path())) > 0:
            # get sword server so we can access pipeline information
            sword_server = SwordServer.objects.get(space=deposit.space)
            result = activate_transfer_and_request_approval_from_pipeline(deposit, sword_server)

            if 'error' in result:
                return _sword_error_response(request, 500, result['message'])

            completed = True

    if completed:
        # mark deposit as complete
        deposit.deposit_completion_time = timezone.now()
    else:
        # make finalization as having failed
        deposit.finalization_attempt_failed = True
    deposit.save()

    return completed

"""
Handle requesting the approval of a transfer from a pipeline via a REST call.

This function returns a dict representation of the results, either returning
the JSON returned by the request to the pipeline (converted to a dict) or
a dict indicating a pipeline authentication issue.

The dict representation is of the form:

{
    'error': <True|False>,
    'message': <description of success or failure>
}
"""
def activate_transfer_and_request_approval_from_pipeline(deposit, sword_server):
    # make sure pipeline API access is configured
    for property in ['remote_name', 'api_username', 'api_key']:
        if getattr(sword_server.pipeline, property)=='':
            property_description = property.replace('_', ' ')
            # TODO: fix this
            return _sword_error_response(request, 500, 'Pipeline {property} not set.'.format(property=property_description))

    # TODO: add error if more than one location is returned
    processing_location = Location.objects.get(
        pipeline=sword_server.pipeline,
        purpose=Location.CURRENTLY_PROCESSING)

    destination_path = os.path.join(
        processing_location.full_path(),
        'watchedDirectories/activeTransfers/standardTransfer',
        os.path.basename(deposit.full_path()))

    # move to standard transfers directory
    destination_path = pad_destination_filepath_if_it_already_exists(destination_path)
    shutil.move(deposit.full_path(), destination_path)

    # wait to make sure the MCP responds to the directory being in the watch directory
    time.sleep(4)

    # make request to pipeline's transfer approval API
    data = urllib.urlencode({
        'username': sword_server.pipeline.api_username,
        'api_key': sword_server.pipeline.api_key,
        'directory': os.path.basename(destination_path),
        'type': 'standard'
    })

    pipeline_endpoint_url = 'http://' + sword_server.pipeline.remote_name + '/api/transfer/approve/'
    approve_request = urllib2.Request(pipeline_endpoint_url, data)

    try:
        approve_response = urllib2.urlopen(approve_request)
    except:
        # move back to deposit directory
        shutil.move(destination_path, deposit.full_path())
        return {
            'error': True,
            'message': 'Request to pipeline ' + sword_server.pipeline.uuid + ' transfer approval API failed: check credentials and REST API IP whitelist.'
        } #_sword_error_response(request, 500, 'Request to pipeline transfer approval API failed: check credentials and REST API IP whitelist.')

    result = json.loads(approve_response.read())
    return result
