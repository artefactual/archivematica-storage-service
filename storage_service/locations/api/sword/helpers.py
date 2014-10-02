# stdlib, alphabetical
import base64
import cgi
import json
import datetime
import logging
import os
from multiprocessing import Process
import shutil
import tempfile
import time
import urllib
import urllib2

# Core Django, alphabetical
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

# External dependencies, alphabetical
from annoying.functions import get_object_or_None
import requests

# This project, alphabetical
from locations import models
from common.utils import generate_checksum

LOGGER = logging.getLogger(__name__)

def get_deposit(uuid):
    """
    Shortcut to retrieve deposit data. Returns deposit model object or None
    """
    return get_object_or_None(models.Package, uuid=uuid)

def deposit_list(location_uuid):
    """
    Retrieve list of deposits

    Returns list containing all deposits in the Location with `location_uuid`.
    """
    # TODO: filter out completed ones?
    deposits = models.Package.objects.filter(
        package_type=models.Package.DEPOSIT).filter(
        current_location_id=location_uuid).exclude(
        status=models.Package.DELETED).exclude(
        status=models.Package.FINALIZED)
    return deposits

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

def parse_filename_from_content_disposition(header):
    """
    Parse a filename from HTTP Content-Disposition data

    Return filename
    """
    _, params = cgi.parse_header(header)
    filename = params.get('filename', '')
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
def download_resource(url, destination_path, filename=None, username=None, password=None):
    LOGGER.info('downloading url: ' + url)
    request = urllib2.Request(url)

    if username != None and password != None:
        base64string = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
        request.add_header("Authorization", "Basic %s" % base64string)   

    response = urllib2.urlopen(request)
    info = response.info()
    if filename == None:
        if 'content-disposition' in info:
            filename = parse_filename_from_content_disposition(info['content-disposition'])
        else:
            filename = os.path.basename(url)
    LOGGER.info('Filename set to ' + filename)

    filepath = os.path.join(destination_path, filename)
    buffer_size = 16 * 1024
    with open(filepath, 'wb') as fp:
        while True:
            chunk = response.read(buffer_size)
            if not chunk:
                break
            fp.write(chunk)
    return filename

def deposit_download_tasks(deposit):
    """
    Return a deposit's download tasks.
    """
    return models.PackageDownloadTask.objects.filter(package=deposit)

def deposit_downloading_status(deposit):
    """
    Return deposit status, indicating whether any incomplete or failed batch
    downloads exist.
    """
    tasks = deposit_download_tasks(deposit)
    # Check each task for completion and failure
    # If any are incomplete or have failed, then return that status
    # If all are complete (or there are no tasks), return completed
    for task in tasks:
        status = task.downloading_status()
        if status != models.PackageDownloadTask.COMPLETE:
            # Status is either models.PackageDownloadTask.FAILED or INCOMPLETE
            return status
    return models.PackageDownloadTask.COMPLETE

def spawn_download_task(deposit_uuid, objects, subdir=None):
    """
    Spawn an asynchrnous batch download
    """
    p = Process(target=_fetch_content, args=(deposit_uuid, objects, subdir))
    p.start()

def _fetch_content(deposit_uuid, objects, subdir=None):
    """
    Download a number of files, keeping track of progress and success using a
    database record. After downloading, finalize deposit if requested.

    If subdir is provided, the file will be moved into a subdirectory of the
    new transfer; otherwise, it will be placed in the transfer's root.
    """
    # add download task to keep track of progress
    deposit = get_deposit(deposit_uuid)
    task = models.PackageDownloadTask(package=deposit)
    task.downloads_attempted = len(objects)
    task.downloads_completed = 0
    task.save()

    # Get deposit protocol info
    deposit_space = deposit.current_location.space.get_child_space()
    fedora_username = getattr(deposit_space, 'fedora_user', None)
    fedora_password = getattr(deposit_space, 'fedora_password', None)

    # download the files
    temp_dir = tempfile.mkdtemp()
    completed = 0
    for item in objects:
        # create download task file record
        task_file = models.PackageDownloadTaskFile(task=task)
        task_file.save()

        try:
            filename = item['filename']

            task_file.filename = filename
            task_file.url = item['url']
            task_file.save()

            download_resource(
                url=item['url'],
                destination_path=temp_dir,
                filename=filename,
                username=fedora_username,
                password=fedora_password
            )

            temp_filename = os.path.join(temp_dir, filename)

            if item['checksum'] is not None and item['checksum'] != generate_checksum(temp_filename, 'md5').hexdigest():
                os.unlink(temp_filename)
                raise Exception("Incorrect checksum")

            # Some MODS records have no proper filenames
            if filename == 'MODS Record':
                filename = item['object_id'].replace(':', '-') + '-MODS.xml'

            if subdir:
                base_path = os.path.join(deposit.full_path(), subdir)
            else:
                base_path = deposit.full_path()

            new_path = os.path.join(base_path, filename)
            shutil.move(temp_filename, new_path)

            # mark download task file record complete or failed
            task_file.completed = True
            task_file.save()

            LOGGER.info('Saved file to ' + new_path)
            completed += 1

            file_record = models.File(
                name=item['filename'],
                source_id=item['object_id'],
                checksum=generate_checksum(new_path, 'sha512').hexdigest()
            )
            file_record.save()
        except Exception as e:
            LOGGER.error('Package download task encountered an error:' + str(e))
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
    ready_for_finalization = deposit.misc_attributes.get('ready_for_finalization', False)
    if ready_for_finalization and deposit_downloading_status(deposit) == models.PackageDownloadTask.COMPLETE:
        _finalize_if_not_empty(deposit_uuid)

def spawn_finalization(deposit_uuid):
    """
    Spawn an asynchronous finalization
    """
    p = Process(target=_finalize_if_not_empty, args=(deposit_uuid, ))
    p.start()

def _finalize_if_not_empty(deposit_uuid):
    """
    Approve a deposit for processing and mark is as completed or finalization failed

    Returns a dict of the form:
    {
        'error': <True|False>,
        'message': <description of success or failure>
    }
    """
    deposit = get_deposit(deposit_uuid)
    completed = False
    result = {
        'error': True,
        'message': 'Deposit empty, or not done downloading.',
    }
    # don't finalize if still downloading
    if deposit_downloading_status(deposit) == models.PackageDownloadTask.COMPLETE:
        if len(os.listdir(deposit.full_path())) > 0:
            # get sword server so we can access pipeline information
            if not deposit.current_location.pipeline.exists():
                return {
                    'error': True,
                    'message': 'No Pipeline associated with this collection'
                }
            pipeline = deposit.current_location.pipeline.all()[0]
            result = activate_transfer_and_request_approval_from_pipeline(deposit, pipeline)
            if result.get('error', False):
                LOGGER.warning('Error creating transfer: %s', result)
            else:
                completed = True

    if completed:
        # mark deposit as complete
        deposit.misc_attributes.update({'deposit_completion_time': timezone.now()})
        deposit.status = models.Package.FINALIZED
    else:
        # make finalization as having failed
        deposit.misc_attributes.update({'finalization_attempt_failed': True})
    deposit.save()

    return result

def activate_transfer_and_request_approval_from_pipeline(deposit, pipeline):
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
    # make sure pipeline API access is configured
    attrs = ('remote_name', 'api_username', 'api_key')
    if not all([getattr(pipeline, attr, None) for attr in attrs]):
        missing_attrs = [a for a in attrs if not getattr(pipeline, a, None)]
        return {
            'error': True,
            'message': 'Pipeline properties {} not set.'.format(', '.join(missing_attrs))
        }

    # TODO: add error if more than one location is returned
    processing_location = models.Location.objects.get(
        pipeline=pipeline,
        purpose=models.Location.CURRENTLY_PROCESSING)

    destination_path = os.path.join(
        processing_location.full_path(),
        'watchedDirectories', 'activeTransfers', 'standardTransfer',
        deposit.current_path)

    # FIXME this should use Space.move_[to|from]_storage_service
    # move to standard transfers directory
    destination_path = pad_destination_filepath_if_it_already_exists(destination_path)
    shutil.move(deposit.full_path(), destination_path)

    params = {
        'username': pipeline.api_username,
        'api_key': pipeline.api_key
    }
    url = 'http://' + pipeline.remote_name + '/api/transfer/unapproved/'
    while True:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            results = response.json()
        else:
            raise Exception("Dashboard returned {}: {}".format(response.status_code, response.text))

        directories = [result['directory'] for result in results['results'] if result['type'] == 'standard']
        if deposit.current_path in directories:
            break
        time.sleep(5)

    # make request to pipeline's transfer approval API
    data = urllib.urlencode({
        'username': pipeline.api_username,
        'api_key': pipeline.api_key,
        'directory': deposit.current_path,
        'type': 'standard'
    })

    pipeline_endpoint_url = 'http://' + pipeline.remote_name + '/api/transfer/approve/'
    approve_request = urllib2.Request(pipeline_endpoint_url, data)
    try:
        approve_response = urllib2.urlopen(approve_request)
    except Exception:
        LOGGER.exception('Automatic approval of transfer for deposit %s failed', deposit.uuid)
        # move back to deposit directory
        # FIXME moving the files out from under Archivematica leaves a transfer that will always error out - leave it?
        shutil.move(destination_path, deposit.full_path())
        return {
            'error': True,
            'message': 'Request to pipeline ' + pipeline.uuid + ' transfer approval API failed: check credentials and REST API IP whitelist.'
        }
    result = json.loads(approve_response.read())
    return result

def sword_error_response(request, status, summary):
    """ Generate SWORD 2.0 error response """
    error_details = {'summary': summary, 'status': status}
    error_details['request'] = request
    error_details['update_time'] = datetime.datetime.now().__str__()
    error_details['user_agent'] = request.META['HTTP_USER_AGENT']
    error_xml = render_to_string('locations/api/sword/error.xml', error_details)
    return HttpResponse(error_xml, status=error_details['status'])

def store_mets_data(mets_path, deposit, object_id):
    submission_documentation_directory = os.path.join(deposit.full_path(), 'submissionDocumentation')
    if not os.path.exists(submission_documentation_directory):
        os.mkdir(submission_documentation_directory)

    mets_name = object_id.replace(':', '-') + '-METS.xml'
    target = os.path.join(submission_documentation_directory, mets_name)

    # There may be a previous METS file if the same file is being
    # re-transferred, so remove and update the METS in this case.
    if os.path.exists(target):
        os.path.unlink(target)

    os.rename(mets_path, target)
