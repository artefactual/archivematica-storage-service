# stdlib, alphabetical
import datetime
import json
from lxml import etree as etree
from multiprocessing import Process
import os
import shutil
import tempfile
import time
import urllib
import urllib2

# Core Django, alphabetical
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

# External dependencies, alphabetical
from annoying.functions import get_object_or_None

# This project, alphabetical
from locations.models import Deposit
from locations.models import Location
from locations.models import Pipeline
from locations.models import Space
import helpers

"""
Example GET of service document:

  curl -v http://127.0.0.1:8000/api/v1/space/969959bc-5f20-4c6f-9e9b-fcc4e19d6cd5/sword/
"""
def service_document(request, space_uuid):
    space = get_object_or_None(Space, uuid=space_uuid)
    if space == None:
        return _sword_error_response(404, 'Space {uuid} does not exist.'.format(uuid=space_uuid))

    locations = Location.objects.filter(space=space)

    collections = []
    for location in locations:
        if location.description != '':
            title = location.description
        else:
            title = 'Collection'

        col_iri = request.build_absolute_uri(
            reverse('sword_collection', kwargs={'api_name': 'v1',
                'resource_name': 'location', 'uuid': location.uuid}))

        collections.append({
            'title': title,
            'url': col_iri
        })

    service_document_xml = render_to_string('locations/api/sword/service_document.xml', locals())
    response = HttpResponse(service_document_xml)
    response['Content-Type'] = 'application/atomserv+xml'
    return response

"""
Example GET of collection deposit list:

  curl -v http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/

Example POST creation of deposit, allowing asynchronous downloading of object content URLs:

  curl -v -H "In-Progress: true" --data-binary @mets.xml --request POST http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/

Example POST creation of deposit, finalizing the deposit and auto-approving it:

  curl -v -H "In-Progress: false" --data-binary @mets.xml --request POST http://localhost:8000/api/v1/location/c0bee7c8-3e9b-41e3-8600-ee9b2c475da2/sword/collection/?approval_pipeline=41b57f04-9738-43d8-b80e-3fad88c75abc
"""
def collection(request, location_uuid):
    location = get_object_or_None(Location, uuid=location_uuid)

    if location == None:
        return _sword_error_response(404, 'Location {uuid} does not exist.'.format(uuid=location_uuid))

    if request.method == 'GET':
        # return list of deposits as ATOM feed
        col_iri = request.build_absolute_uri(
            reverse('sword_collection', kwargs={'api_name': 'v1',
                'resource_name': 'location', 'uuid': location_uuid}))

        feed = {
            'title': 'Deposits',
            'url': col_iri
        }

        entries = []

        for uuid in helpers.deposit_list(location_uuid):
            deposit = Deposit.objects.get(uuid=uuid)

            edit_iri = request.build_absolute_uri(
                reverse('sword_deposit', kwargs={'api_name': 'v1',
                    'resource_name': 'deposit', 'uuid': uuid}))

            entries.append({
                'title': deposit.name,
                'url': edit_iri,
            })

        collection_xml = render_to_string('locations/api/sword/collection.xml', locals())
        response = HttpResponse(collection_xml)
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response
    elif request.method == 'POST':
        # has the In-Progress header been set?
        if 'HTTP_IN_PROGRESS' in request.META:
            # process creation request, if criteria met
            if request.body != '':
                try:
                    temp_filepath = helpers.write_request_body_to_temp_file(request)

                    # parse name and content URLs out of XML
                    try:
                        tree = etree.parse(temp_filepath)
                        root = tree.getroot()
                        deposit_name = root.get('LABEL')

                        if deposit_name == None:
                            return _sword_error_response(400, 'No deposit name found in XML.')
                        else:
                            # assemble deposit specification
                            deposit_specification = {'location_uuid': location_uuid}
                            deposit_specification['name'] = deposit_name
                            if 'HTTP_ON_BEHALF_OF' in request.META:
                                # TODO: should get this from author header
                                deposit_specification['sourceofacquisition'] = request.META['HTTP_ON_BEHALF_OF']

                            if not os.path.isdir(location.full_path()):
                                return  _sword_error_response(500, 'Location path (%s) does not exist: contact an administrator.' % (location.full_path()))
                            else:
                                deposit_uuid = _create_deposit_directory_and_db_entry(deposit_specification)

                                if deposit_uuid != None:
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

                                    if request.META['HTTP_IN_PROGRESS'] == 'true':
                                        # create subprocess so content URLs can be downloaded asynchronously
                                        p = Process(target=_fetch_content, args=(deposit_uuid, object_content_urls))
                                        p.start()
                                        return _deposit_receipt_response(request, deposit_uuid, 201)
                                    else:
                                        # fetch content synchronously then finalize transfer
                                        _fetch_content(deposit_uuid, object_content_urls)
                                        return deposit_edit(request, deposit_uuid)
                                else:
                                    return _sword_error_response(500, 'Could not create deposit: contact an administrator.')
                    except etree.XMLSyntaxError as e:
                        return _sword_error_response(412, 'Error parsing XML ({error_message}).'.format(error_message=str(e)))
                except Exception as e:
                    import sys
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    return _sword_error_response(400, 'Contact administration: ' + str(exc_type) + ' ' + str(fname) + ' ' + str(exc_tb.tb_lineno))
            else:
                return _sword_error_response(412, 'A request body must be sent when creating a deposit.')
        else:
            return _sword_error_response(412, 'The In-Progress header must be set to either true or false when creating a deposit.')
    else:
        return _sword_error_response(405, 'This endpoint only responds to the GET and POST HTTP methods.')

def _create_deposit_directory_and_db_entry(deposit_specification):
    if 'name' in deposit_specification:
        deposit_name = deposit_specification['name']
    else:
        deposit_name = 'Untitled'

    location = Location.objects.get(uuid=deposit_specification['location_uuid']) 

    deposit_path = os.path.join(
        location.full_path(),
        deposit_name
    )

    deposit_path = helpers.pad_destination_filepath_if_it_already_exists(deposit_path)
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

def _fetch_content(deposit_uuid, object_content_urls):
    # update deposit with number of files that need to be downloaded
    deposit = Deposit.objects.get(uuid=deposit_uuid)
    deposit.downloads_attempted = len(object_content_urls)
    deposit.downloads_completed = 0
    deposit.save()

    # download the files
    temp_dir = tempfile.mkdtemp()

    completed = 0
    for url in object_content_urls:
        try:
            filename = helpers.download_resource(url, temp_dir)
            completed += 1
        except:
            pass
        shutil.move(os.path.join(temp_dir, filename),
            os.path.join(deposit.full_path(), filename))

    # remove temp dir
    shutil.rmtree(temp_dir)

    # record the number of successful downloads and completion time
    deposit.downloads_completed = completed
    deposit.download_completion_time = timezone.now()
    deposit.save()

"""
Example POST finalization of deposit:

  curl -v -H "In-Progress: false" --request POST http://127.0.0.1:8000/api/v1/deposit/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/

Example DELETE of deposit:

  curl -v -XDELETE http://127.0.0.1:8000/api/v1/deposit/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/
"""
def deposit_edit(request, uuid):
    deposit = get_object_or_None(Deposit, uuid=uuid)

    if deposit == None:
        return _sword_error_response(404, 'Deposit {uuid} does not exist.'.format(uuid=uuid))

    if deposit.has_been_submitted_for_processing():
        return _sword_error_response(400, 'This deposit has already been submitted for processing.')

    if request.method == 'GET':
        # details about a deposit
        return HttpResponse('Feed XML of files for deposit' + uuid)
    elif request.method == 'POST':
        # is the deposit ready to be processed?
        if 'HTTP_IN_PROGRESS' in request.META and request.META['HTTP_IN_PROGRESS'] == 'false':
            # TODO: check that async download is complete before copying
            deposit = Deposit.objects.get(uuid=uuid)

            if len(os.listdir(deposit.full_path())) > 0:
                # optionally auto-approve
                approval_pipeline = request.GET.get('approval_pipeline', '')

                # if auto-approve is being used, test configuration
                if approval_pipeline != '':
                    try:
                        pipeline = Pipeline.objects.get(uuid=approval_pipeline)
                    except ObjectDoesNotExist:
                        return _sword_error_response(400, 'Pipeline {uuid} does not exist.'.format(uuid=approval_pipeline))

                    # make sure pipeline API access is configured
                    for property in ['remote_name', 'api_username', 'api_key']:
                        if getattr(pipeline, property)=='':
                            property_description = property.replace('_', ' ')
                            return _sword_error_response(500, 'Pipeline {property} not set.'.format(property=property_description))

                # TODO... how to get appropriate destination path?
                destination_path = '/var/archivematica/sharedDirectory/watchedDirectories/activeTransfers/standardTransfer/' + os.path.basename(deposit.full_path())

                # move to standard transfers directory
                destination_path = helpers.pad_destination_filepath_if_it_already_exists(destination_path)
                shutil.move(deposit.full_path(), destination_path)

                # handle auto-approval
                if approval_pipeline != '':
                    # wait to make sure the MCP responds to the directory being in the watch directory
                    time.sleep(2)

                    # make request to pipeline's transfer approval API
                    data = urllib.urlencode({
                        'username': pipeline.api_username,
                        'api_key': pipeline.api_key,
                        'directory': os.path.basename(destination_path),
                        'type': 'standard' # TODO: make this customizable via a URL param
                    })
                    approve_request = urllib2.Request('http://' + pipeline.remote_name + '/api/transfer/approve/', data)

                    try:
                        approve_response = urllib2.urlopen(approve_request)
                    except:
                        return _sword_error_response(500, 'Request to pipeline transfer approval API failed: check credentials.')

                    result = json.loads(approve_response.read())
                    if 'error' in result:
                        return _sword_error_response(500, result['message'])

                # mark deposit as complete and return deposit receipt
                deposit.deposit_completion_time = timezone.now()
                deposit.save()
                return _deposit_receipt_response(request, uuid, 200)
            else:
                return _sword_error_response(400, 'This deposit contains no files.')
        else:
            return _sword_error_response(400, 'The In-Progress header must be set to false when starting deposit processing.')
    elif request.method == 'PUT':
        # TODO: implement update deposit
        return HttpResponse(status=204) # No content
    elif request.method == 'DELETE':
        # delete deposit files
        shutil.rmtree(deposit.full_path())

        # delete deposit
        deposit = Deposit.objects.get(uuid=uuid)
        deposit.delete()

        return HttpResponse(status=204) # No content
    else:
        return _sword_error_response(405, 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.')

"""
Example GET of files list:

  curl -v http://127.0.0.1:8000/api/v1/deposit/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/media/

Example POST of file:

  curl -v -H "Content-Disposition: attachment; filename=joke.jpg" --request POST \
    --data-binary "@joke.jpg" \
    http://127.0.0.1:8000/api/v1/deposit/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

Example DELETE of all files:

  curl -v -XDELETE \
    http://127.0.0.1:8000/api/v1/deposit/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

Example DELETE of file:

  curl -v -XDELETE \
    http://127.0.0.1:8000/api/v1/deposit/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/?filename=joke.jpg
"""
def deposit_media(request, uuid):
    deposit = get_object_or_None(Deposit, uuid=uuid)

    if deposit == None:
        return _sword_error_response(404, 'Deposit {uuid} does not exist.'.format(uuid=uuid))

    if deposit.has_been_submitted_for_processing():
        return _sword_error_response(400, 'This deposit has already been submitted for processing.')

    if request.method == 'GET':
        return HttpResponse(str(os.listdir(deposit.full_path())))
    elif request.method == 'PUT':
        # replace a file in the deposit
        return _handle_upload_request(request, uuid, True)
    elif request.method == 'POST':
        # add a file to the deposit
        return _handle_upload_request(request, uuid)
    elif request.method == 'DELETE':
        filename = request.GET.get('filename', '')
        if filename != '':
            file_path = os.path.join(deposit.full_path(), filename) 
            if os.path.exists(file_path):
                os.remove(file_path)
                return HttpResponse(status=204) # No content
            else:
                return _sword_error_response(404, 'The path to this file (%s) does not exist.' % (file_path))
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
        return _sword_error_response(405, 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.')

def _handle_upload_request(request, deposit, replace_file=False):
    if 'HTTP_CONTENT_DISPOSITION' in request.META:
        filename = helpers.parse_filename_from_content_disposition(request.META['HTTP_CONTENT_DISPOSITION']) 

        if filename != '':
            file_path = os.path.join(deposit.full_path(), filename)

            if replace_file:
                # if doing a file replace, the file being replaced must exist
                if os.path.exists(file_path):
                    return _handle_upload_request_with_potential_md5_checksum(
                        request,
                        file_path,
                        204
                    )
                else:
                    return _sword_error_response(400, 'File does not exist.')
            else:
                # if adding a file, the file must not already exist
                if os.path.exists(file_path):
                    return _sword_error_response(400, 'File already exists.')
                else:
                    return _handle_upload_request_with_potential_md5_checksum(
                        request,
                        file_path,
                        201
                    )
        else:
            return _sword_error_response(400, 'No filename found in Content-disposition header.')
    else:
        return _sword_error_response(400, 'Content-disposition must be set in request header.')

def _handle_upload_request_with_potential_md5_checksum(request, file_path, success_status_code):
    temp_filepath = helpers.write_request_body_to_temp_file(request)
    if 'HTTP_CONTENT_MD5' in request.META:
        md5sum = helpers.get_file_md5_checksum(temp_filepath)
        if request.META['HTTP_CONTENT_MD5'] != md5sum:
            os.remove(temp_filepath)
            return _sword_error_response(400, 'MD5 checksum of uploaded file ({uploaded_md5sum}) does not match ' + 'checksum provided in header ({header_md5sum}).'.format(
                uploaded_md5sum=md5sum, header_md5sum=request.META['HTTP_CONTENT_MD5']))
        else:
            shutil.copyfile(temp_filepath, file_path)
            os.remove(temp_filepath)
            return HttpResponse(status=success_status_code)
    else:
        shutil.copyfile(temp_filepath, file_path)
        os.remove(temp_filepath)
        return HttpResponse(status=success_status_code)

"""
Example GET of state:

  curl -v http://localhost:8000/api/v1/deposit/96606387-cc70-4b09-b422-a7220606488d/sword/state/
"""
def deposit_state(request, uuid):
    deposit = get_object_or_None(Deposit, uuid=uuid)

    if deposit == None:
        return _sword_error_response('This deposit has already been submitted for processing.'(404, 'Deposit {uuid} does not exist.'.format(uuid=uuid)))

    if request.method == 'GET':
        """
        In order to determine the deposit status we need to check
        for three possibilities:
        
        1) The deposit involved no asynchronous depositing. The
           downloads_attempted DB row column should be 0.
       
        2) The deposit involved asynchronous depositing, but
           the depositing is incomplete. downloads_attempted is
           greater than 0, but download_completion_time is not
           set.
      
        3) The deposit involved asynchronous depositing and
           completed successfully. download_completion_time is set.
           downloads_attempted is equal to downloads_completed.
      
        4) The deposit involved asynchronous depositing and
           completed unsuccessfully. download_completion_time is set.
           downloads_attempted isn't equal to downloads_completed.
        """
        deposit = Deposit.objects.get(uuid=uuid)
        if deposit.downloads_attempted == 0:
            task_state = 'Complete'
        else:
           if deposit.download_completion_time == None:
               task_state = 'Incomplete'
           else:
               if deposit.downloads_attempted == deposit.downloads_completed:
                   task_state = 'Complete'
               else:
                   task_state = 'Failed'

        state_term = task_state.lower()
        state_description = 'Deposit initiation: ' + task_state

        response = HttpResponse(render_to_string('locations/api/sword/state.xml', locals()))
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response
    else:
        return _sword_error_response(405, 'This endpoint only responds to the GET HTTP method.')

# respond with SWORD 2.0 deposit receipt XML
def _deposit_receipt_response(request, deposit_uuid, status_code):
    deposit = Deposit.objects.get(uuid=deposit_uuid)

    # TODO: fix minor issues with template
    media_iri = request.build_absolute_uri(
        reverse('sword_deposit_media', kwargs={'api_name': 'v1',
            'resource_name': 'deposit', 'uuid': deposit_uuid}))

    edit_iri = request.build_absolute_uri(
        reverse('sword_deposit', kwargs={'api_name': 'v1',
            'resource_name': 'deposit', 'uuid': deposit_uuid}))

    state_iri = request.build_absolute_uri(
        reverse('sword_deposit_state', kwargs={'api_name': 'v1',
            'resource_name': 'deposit', 'uuid': deposit_uuid}))

    receipt_xml = render_to_string('locations/api/sword/deposit_receipt.xml', locals())

    response = HttpResponse(receipt_xml, mimetype='text/xml', status=status_code)
    response['Location'] = deposit_uuid
    return response

def _sword_error_response_render(request, error_details):
    error_details['request'] = request
    error_details['update_time'] = datetime.datetime.now().__str__()
    error_details['user_agent'] = request.META['HTTP_USER_AGENT']
    error_xml = render_to_string('locations/api/sword/error.xml', error_details)
    return HttpResponse(error_xml, status=error_details['status'])

def _sword_error_response(status, summary):
    error = _error(status, summary)
    return _sword_error_response_render(request, error)

def _error(status, summary):
    return {
        'summary': summary,
        'status': status
    }
