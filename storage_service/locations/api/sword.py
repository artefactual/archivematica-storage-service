# stdlib, alphabetical
import datetime
from lxml import etree as etree
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

# Core Django, alphabetical
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

# This project, alphabetical
from ..models import Deposit
from ..models import Location

def _deposit_storage_path(uuid):
    try:
        deposit = Deposit.objects.get(uuid=uuid)
        return deposit.full_path()
    except ObjectDoesNotExist:
        return None

def _deposit_storage_path_root(location_uuid):
    location = Location.objects.get(uuid=location_uuid)
    return location.full_path()

def _create_deposit_directory_and_db_entry(deposit_specification):
    deposit_uuid = uuid.uuid4().__str__()

    if 'name' in deposit_specification:
        deposit_name = deposit_specification['name']
    else:
        deposit_name = 'Untitled'

    deposit_path = os.path.join(
        _deposit_storage_path_root(deposit_specification['location_uuid']),
        deposit_name
    )

    # TODO deposit_path = helpers.pad_destination_filepath_if_it_already_exists(deposit_path)
    os.mkdir(deposit_path)
    os.chmod(deposit_path, 02770) # drwxrws---

    if os.path.exists(deposit_path):
        location = Location.objects.get(uuid=deposit_specification['location_uuid'])
        deposit = Deposit.objects.create(name=deposit_name, path=deposit_name,
            location=location)

        # TODO
        if 'sourceofacquisition' in deposit_specification:
            deposit.source = deposit_specification['sourceofacquisition']

        deposit.save()
        return deposit.uuid

def _deposit_list(location_uuid):
    location = Location.objects.get(uuid=location_uuid)

    deposit_list = []
    deposits = Deposit.objects.filter(location=location)
    for deposit in deposits:
        deposit_list.append(deposit.uuid)
    return deposit_list

def _sword_error_response(request, error_details):
    error_details['request'] = request
    error_details['update_time'] = datetime.datetime.now().__str__()
    error_details['user_agent'] = request.META['HTTP_USER_AGENT']
    error_xml = render_to_string('locations/api/sword/error.xml', error_details)
    return HttpResponse(error_xml, status=error_details['status'])

def _write_file_from_request_body(request, file_path):
    bytes_written = 0
    new_file = open(file_path, 'ab')
    chunk = request.read()
    if chunk != None:
        new_file.write(chunk)
        bytes_written += len(chunk)
        chunk = request.read()
    new_file.close()
    return bytes_written

def _get_file_md5_checksum(filepath):
    raw_result = subprocess.Popen(["md5sum", filepath],stdout=subprocess.PIPE).communicate()[0]
    return raw_result[0:32]

def _handle_upload_request_with_potential_md5_checksum(request, file_path, success_status_code):
    temp_filepath = _write_request_body_to_temp_file(request)
    if 'HTTP_CONTENT_MD5' in request.META:
        md5sum = _get_file_md5_checksum(temp_filepath)
        if request.META['HTTP_CONTENT_MD5'] != md5sum:
            os.remove(temp_filepath)
            bad_request = 'MD5 checksum of uploaded file ({uploaded_md5sum}) does not match checksum provided in header ({header_md5sum}).'.format(uploaded_md5sum=md5sum, header_md5sum=request.META['HTTP_CONTENT_MD5'])
            return _sword_error_response(request, {
                'summary': bad_request,
                'status': 400
            })
        else:
            shutil.copyfile(temp_filepath, file_path)
            os.remove(temp_filepath)
            return HttpResponse(status=success_status_code)
    else:
        shutil.copyfile(temp_filepath, file_path)
        os.remove(temp_filepath)
        return HttpResponse(status=success_status_code)

def _parse_filename_from_content_disposition(header):
    filename = header.split('filename=')[1]
    if filename[0] == '"' or filename[0] == "'":
            filename = filename[1:-1]
    return filename

def _handle_upload_request(request, uuid, replace_file=False):
    error = None
    bad_request = None

    if 'HTTP_CONTENT_DISPOSITION' in request.META:
        filename = _parse_filename_from_content_disposition(request.META['HTTP_CONTENT_DISPOSITION']) 

        if filename != '':
            file_path = os.path.join(_deposit_storage_path(uuid), filename)

            if replace_file:
                # if doing a file replace, the file being replaced must exist
                if os.path.exists(file_path):
                    return _handle_upload_request_with_potential_md5_checksum(
                        request,
                        file_path,
                        204
                    )
                else:
                    bad_request = 'File does not exist.'
            else:
                # if adding a file, the file must not already exist
                if os.path.exists(file_path):
                    bad_request = 'File already exists.'
                else:
                    return _handle_upload_request_with_potential_md5_checksum(
                        request,
                        file_path,
                        201
                    )
        else:
            bad_request = 'No filename found in Content-disposition header.'
    else:
        bad_request = 'Content-disposition must be set in request header.'

    if bad_request != None:
        error = {
            'summary': bad_request,
            'status': 400
        }

    if error != None:
        return _sword_error_response(request, error)

def _write_request_body_to_temp_file(request):
    filehandle, temp_filepath = tempfile.mkstemp()
    _write_file_from_request_body(request, temp_filepath)
    return temp_filepath

def _fetch_content(transfer_uuid, object_content_urls):
    # write resources to temp file
    temp_dir = tempfile.mkdtemp()
    os.chmod(temp_dir, 02770) # drwxrws---

    # create job record to associate tasks with the transfer
    now = datetime.datetime.now()
    job_uuid = uuid.uuid4().__str__()
    job = models.Job()
    job.jobuuid = job_uuid
    job.sipuuid = transfer_uuid
    job.createdtime = now.__str__()
    job.createdtimedec = int(now.strftime("%s"))
    job.hidden = True
    job.save()

    for resource_url in object_content_urls:
        # create task record so progress can be tracked
        task_uuid = uuid.uuid4().__str__()
        arguments = '"{resource_url}" "{transfer_path}"'.format(resource_url=resource_url, transfer_path=_deposit_storage_path(transfer_uuid))

        """
        # create task record so time can be tracked by the MCP client
        # ...Django doesn't like putting 0 in datetime fields
        # TODO: put in arguments, etc. and use proper sanitization
        sql = "INSERT INTO Tasks (taskUUID, jobUUID, startTime) VALUES ('%s', '%s', 0)" % (task_uuid, job_uuid)
        #sql = "INSERT INTO Tasks (taskUUID, jobUUID, startTime) VALUES ('" + task_uuid + "', '" + job_uuid + "', 0)"
        databaseInterface.runSQL(sql)
        _flush_transaction() # refresh ORM after manual SQL

        command = '/usr/lib/archivematica/MCPClient/clientScripts/fetchFedoraCommonsObjectContent.py ' + arguments
        exitCode, stdOut, stdError = executeOrRun("command", command)

        # record task completion time
        task = models.Task.objects.get(taskuuid=task_uuid)
        task.exitcode = exitCode
        task.endtime = datetime.datetime.now().__str__() # TODO: endtime seems weird... Django time zone issue?
        task.save()
        """

    # delete temp dir
    shutil.rmtree(temp_dir)

# respond with SWORD 2.0 deposit receipt XML
def _deposit_receipt_response(request, deposit_uuid, status_code):
    media_iri = request.build_absolute_uri(
       reverse('sword_deposit_media', kwargs={'api_name': 'v1',
           'resource_name': 'deposit', 'uuid': deposit_uuid}))

    edit_iri = request.build_absolute_uri(
        reverse('sword_deposit', kwargs={'api_name': 'v1',
                   'resource_name': 'deposit', 'uuid': deposit_uuid}))

    """
    state_iri = request.build_absolute_uri(
        reverse('components.api.views_sword.transfer_state', args=[transfer_uuid])
    )
    """

    receipt_xml = render_to_string('locations/api/sword/deposit_receipt.xml', locals())

    response = HttpResponse(receipt_xml, mimetype='text/xml', status=status_code)
    response['Location'] = deposit_uuid
    return response

def _deposit_has_been_submitted_for_processing(deposit_uuid):
    try:
        deposit = models.Deposit.objects.get(uuid=deposit_uuid)
        if deposit.status != 'complete':
            return True
        return False
    except:
        return False

"""
Example GET of service document:

  curl -v http://127.0.0.1/api/v2/sword
"""
def service_document(request):
    transfer_collectiion_url = request.build_absolute_uri(
        reverse('components.api.views_sword.transfer_collection')
    )

    service_document_xml = render_to_string('api/sword/service_document.xml', locals())
    response = HttpResponse(service_document_xml)
    response['Content-Type'] = 'application/atomserv+xml'
    return response

"""
Example GET of collection deposit list:

  curl -v http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/

Example POST creation of deposit:

  curl -v -H "In-Progress: true" --data-binary @mets.xml --request POST http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/
"""
# TODO: add authentication
# TODO: error if deposit is finalized, but has no files?
def collection(request, location_uuid):
    error = None
    bad_request = None

    if request.method == 'GET':
        # return list of transfers as ATOM feed
        feed = {
            'title': 'Transfers',
            #'url': request.build_absolute_uri(reverse('components.api.views_sword.transfer_collection'))
        }

        entries = []

        entries = [{
            'title': 'Hey',
            'url': 'http://www.google.com'
        }]
        for uuid in _deposit_list(location_uuid):
            deposit = Deposit.objects.get(uuid=uuid)
            entries.append({
                'title': deposit.name,
                'url': 'http://www.google.com/',
                #'url': request.build_absolute_uri(reverse('components.api.views_sword.transfer', args=[uuid]))
            })

        collection_xml = render_to_string('locations/api/sword/collection.xml', locals())
        response = HttpResponse(collection_xml)
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response
    elif request.method == 'POST':
        # is the deposit still in progress?
        if 'HTTP_IN_PROGRESS' in request.META and request.META['HTTP_IN_PROGRESS'] == 'true':
            # process creation request, if criteria met
            if request.body != '':
                try:
                    temp_filepath = _write_request_body_to_temp_file(request)

                    # parse XML
                    try:
                        tree = etree.parse(temp_filepath)
                        root = tree.getroot()
                        transfer_name = root.get('LABEL')

                        if transfer_name == None:
                            bad_request = 'No deposit name found in XML.'
                        else:
                            # assemble deposit specification
                            transfer_specification = {'location_uuid': location_uuid}
                            transfer_specification['name'] = transfer_name
                            if 'HTTP_ON_BEHALF_OF' in request.META:
                                # TODO: should get this from author header
                                transfer_specification['sourceofacquisition'] = request.META['HTTP_ON_BEHALF_OF']

                            location_path = _deposit_storage_path_root(location_uuid)
                            if not os.path.isdir(location_path):
                                error = {
                                    'summary': 'Location path (%s) does not exist: contact an administrator.' % (location_path),
                                    'status': 500
                                }
                            else:
                                transfer_uuid = _create_deposit_directory_and_db_entry(transfer_specification)

                                if transfer_uuid != None:
                                    # parse XML for content URLs
                                    object_content_urls = []

                                    elements = root.iterfind("{http://www.loc.gov/METS/}fileSec/"
                                        + "{http://www.loc.gov/METS/}fileGrp[@ID='DATASTREAMS']/"
                                        + "{http://www.loc.gov/METS/}fileGrp[@ID='OBJ']/"
                                        + "{http://www.loc.gov/METS/}file/"
                                        + "{http://www.loc.gov/METS/}FLocat"
                                    )

                                    for element in elements:
                                        object_content_urls.append(element.get('{http://www.w3.org/1999/xlink}href'))

                                    # create thread so content URLs can be downloaded asynchronously
                                    thread = threading.Thread(target=_fetch_content, args=(transfer_uuid, object_content_urls))
                                    thread.start()

                                    return _deposit_receipt_response(request, transfer_uuid, 201)
                                else:
                                    error = {
                                        'summary': 'Could not create deposit: contact an administrator.',
                                        'status': 500
                                    }
                    except etree.XMLSyntaxError as e:
                        error = {
                            'summary': 'Error parsing XML ({error_message}).'.format(error_message=str(e)),
                            'status': 412
                        }
                except Exception as e:
                    bad_request = str(e)
            else:
                error = {
                    'summary': 'A request body must be sent when creating a transfer.',
                    'status': 412
                }
        else:
            # TODO: way to do one-step transfer creation by setting In-Progress to false
            error = {
                'summary': 'The In-Progress header must be set to true when creating a transfer.',
                'status': 412
            }
    else:
        error = {
            'summary': 'This endpoint only responds to the GET and POST HTTP methods.',
            'status': 405
        }

    if bad_request != None:
        error = {
            'summary': bad_request,
            'status': 400
        }

    if error != None:
        return _sword_error_response(request, error)

"""
TODO: decouple deposits and locations for shorter URLs

Example POST finalization of transfer:

  curl -v -H "In-Progress: false" --request POST http://127.0.0.1/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/deposit/5bdf83cd-5858-4152-90e2-c2426e90e7c0/

Example DELETE if transfer:

  curl -v -XDELETE http://127.0.0.1/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/deposit/5bdf83cd-5858-4152-90e2-c2426e90e7c0/
"""
# TODO: add authentication
def deposit(request, uuid):
    error = None
    bad_request = None

    if request.method == 'GET':
        # details about a deposit
        return HttpResponse('Feed XML of files for deposit' + uuid)
    elif request.method == 'POST':
        # is the deposit ready to be processed?
        if 'HTTP_IN_PROGRESS' in request.META and request.META['HTTP_IN_PROGRESS'] == 'false':
            # TODO: check that related tasks are complete before copying
            # ...task row must exist and task endtime must be equal to or greater than start time
            try:
                if _deposit_has_been_submitted_for_processing(uuid):
                    error = {
                        'summary': 'This deposit has already been submitted for processing.',
                        'status': 400
                    }
                else:
                    deposit = Deposit.objects.get(uuid=uuid)

                    if len(os.listdir(deposit.full_path())) > 0:
                        """
                        TODO: replace this will call to dashboard API
                        helpers.copy_to_start_transfer(transfer.currentlocation, 'standard', {'uuid': uuid})

                        # wait for watch directory to determine a transfer is awaiting
                        # approval then attempt to approve it
                        time.sleep(5)
                        approve_transfer_via_mcp(
                            os.path.basename(transfer.currentlocation),
                            'standard',
                        1
                        ) # TODO: replace hardcoded user ID
                        """
                        pass

                        return _deposit_receipt_response(request, uuid, 200)
                    else:
                        bad_request = 'This deposit contains no files.'

            except ObjectDoesNotExist:
                error = {
                    'summary': 'This deposit could not be found.',
                    'status': 404
                }
        else:
            bad_request = 'The In-Progress header must be set to false when starting deposit processing.'
    elif request.method == 'PUT':
        # update deposit
        return HttpResponse(status=204) # No content
    elif request.method == 'DELETE':
        # delete deposit files
        deposit_path = _deposit_storage_path(uuid)
        shutil.rmtree(deposit_path)

        # delete entry in Transfers table (and task?)
        deposit = Deposit.objects.get(uuid=uuid)
        deposit.delete()
        return HttpResponse(status=204) # No content
    else:
        error = {
            'summary': 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.',
            'status': 405
        }

    if bad_request != None:
        error = {
            'summary': bad_request,
            'status': 400
        }

    if error != None:
                return _sword_error_response(request, error)

"""
Example GET of files list:

  curl -v http://127.0.0.1/api/v2/transfer/sword/03ce11a5-32c1-445a-83ac-400008894f78/media

Example POST of file:

  curl -v -H "Content-Disposition: attachment; filename=joke.jpg" --request POST \
    --data-binary "@joke.jpg" \
    http://localhost/api/v2/transfer/sword/03ce11a5-32c1-445a-83ac-400008894f78/media

Example DELETE of all files:

  curl -v -XDELETE \
      "http://localhost/api/v2/transfer/sword/03ce11a5-32c1-445a-83ac-400008894f78/media

Example DELETE of file:

  curl -v -XDELETE \
    "http://localhost/api/v2/transfer/sword/03ce11a5-32c1-445a-83ac-400008894f78/media?filename=thing.jpg"
"""
# TODO: implement Content-MD5 header so we can verify file upload was successful
# TODO: better Content-Disposition header parsing
# TODO: add authentication
def deposit_media(request, uuid):
    if _deposit_has_been_submitted_for_processing(uuid):
        return _sword_error_response(request, {
            'summary': 'This deposit has already been submitted for processing.',
            'status': 400
        })

    error = None

    if request.method == 'GET':
        deposit_path = _deposit_storage_path(uuid)
        if deposit_path == None:
            error = {
                'summary': 'This deposit does not exist.',
                'status': 404
            }
        else:
            if os.path.exists(deposit_path):
                return HttpResponse(str(os.listdir(deposit_path)))
                #return helpers.json_response(os.listdir(deposit_path))
            else:
                error = {
                    'summary': 'This deposit path (%s) does not exist.' % (deposit_path),
                    'status': 404
                }
    elif request.method == 'PUT':
        # replace a file in the deposit
        return _handle_upload_request(request, uuid, True)
    elif request.method == 'POST':
        # add a file to the deposit
        return _handle_upload_request(request, uuid)
    elif request.method == 'DELETE':
        filename = request.GET.get('filename', '')
        if filename != '':
            deposit_path = _deposit_storage_path(uuid)
            file_path = os.path.join(deposit_path, filename) 
            if os.path.exists(file_path):
                os.remove(file_path)
                return HttpResponse(status=204) # No content
            else:
                error = {
                    'summary': 'The path to this file (%s) does not exist.' % (file_path),
                    'status': 404
                }
        else:
            # delete all files in deposit
            if _deposit_has_been_submitted_for_processing(uuid):
                error = {
                    'summary': 'This deposit has already been submitted for processing.',
                    'status': 400
                }
            else:
                deposit = Deposit.objects.get(uuid=uuid)

                for filename in os.listdir(deposit.full_path()):
                    filepath = os.path.join(deposit.full_path(), filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                    elif os.path.isdir(filepath):
                        shutil.rmtree(filepath)

                return HttpResponse(status=204) # No content
    else:
        error = {
            'summary': 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.',
            'status': 405
        }

    if error != None:
                return _sword_error_response(request, error)

"""
Example GET of state:

  curl -v http://127.0.0.1/api/v2/transfer/sword/03ce11a5-32c1-445a-83ac-400008894f78/state
"""
# TODO: add authentication
def transfer_state(request, uuid):
    # TODO: add check if UUID is valid, 404 otherwise

    error = None

    if request.method == 'GET':
        # In order to determine the transfer status we need to check
        # for three possibilities:
        #
        # 1) The transfer involved no asynchronous depositing. There
        #    should be no row in the Jobs table for this transfer.
        #
        # 2) The transfer involved asynchronous depositing, but the
        #    depositing is incomplete. There should be a row in the
        #    Jobs table, but the end time should be blank.
        #
        # 3) The transfer involved asynchronous depositing and is
        #    complete. There should be a row in the Jobs table with
        #    an end time.

        # get transfer creation job, if any
        job = None
        try:
            # get job corresponding to transfer
            job = models.Job.objects.filter(sipuuid=uuid, hidden=True)[0]

            task = None
            if job != None:
                try:
                    task = models.Task.objects.filter(job=job)[0]
                except:
                    pass

            if task != None:
                task_state = 'Processing'

            if task.endtime != None:
                if task.exitcode == 1:
                    task_state = 'Failed'
                else:
                    task_state = 'Complete'
        except:
            task_state = 'Complete'

        state_term = task_state.lower()
        state_description = 'Deposit initiation: ' + task_state

        response = HttpResponse(render_to_string('api/sword/state.xml', locals()))
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response
    else:
        error = {
            'summary': 'This endpoint only responds to the GET HTTP method.',
            'status': 405
        }

    if error != None:
                return _sword_error_response(request, error)
