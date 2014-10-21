# stdlib, alphabetical
import logging
from lxml import etree as etree
import os
import shutil
import traceback

# Core Django, alphabetical
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

# External dependencies, alphabetical

# This project, alphabetical
import helpers
from locations import models

LOGGER = logging.getLogger(__name__)
logging.basicConfig(filename="/tmp/storage_service.log",
    level=logging.INFO)


def service_document(request):
    """
    Service document endpoint: returns a list of all SWORD2 collections available.

    Each collection maps to a Location with purpose Location.SWORD_DEPOSIT,
    inside a Space with access_protocol Space.FEDORA

    Example GET of service document:
      curl -v http://127.0.0.1:8000/api/v1/sword/
    """
    locations = models.Location.active.filter(purpose=models.Location.SWORD_DEPOSIT).filter(space__access_protocol=models.Space.FEDORA)

    collections = []
    for location in locations:
        title = location.description or 'Collection'

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

def collection(request, location):
    """
    Collection endpoint: accepts deposits, and returns current deposits.

    Example GET of collection deposit list:
      curl -v http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/

    Example POST creation of deposit, allowing asynchronous downloading of object content URLs:
      curl -v -H "In-Progress: true" --data-binary @mets.xml --request POST http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/

    Example POST creation of deposit, finalizing the deposit and auto-approving it:
      curl -v -H "In-Progress: false" --data-binary @mets.xml --request POST http://localhost:8000/api/v1/location/c0bee7c8-3e9b-41e3-8600-ee9b2c475da2/sword/collection/

    Example POST creation of deposit from another location:
      curl -v -H "In-Progress: true" --request POST http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/collection/?source_location=aab142a9-018f-4452-8f93-67c1bf7fd486&relative_path_to_files=archivematica-sampledata/SampleTransfers/Images
    """
    if isinstance(location, basestring):
        try:
            location = models.Location.active.get(uuid=location)
        except models.Location.DoesNotExist:
            return helpers.sword_error_response(request, 404, 'Collection {uuid} does not exist.'.format(uuid=location))

    if request.method == 'GET':
        # return list of deposits as ATOM feed
        col_iri = request.build_absolute_uri(
            reverse('sword_collection', kwargs={'api_name': 'v1',
                'resource_name': 'location', 'uuid': location.uuid}))
        feed = {
            'title': 'Deposits',
            'url': col_iri
        }

        entries = []
        for deposit in helpers.deposit_list(location.uuid):
            edit_iri = request.build_absolute_uri(
                reverse('sword_deposit', kwargs={'api_name': 'v1',
                    'resource_name': 'file', 'uuid': deposit.uuid}))

            entries.append({
                'title': deposit.description or 'Deposit '+deposit.uuid,
                'url': edit_iri,
            })

        # feed and entries passed via locals() to the template
        collection_xml = render_to_string('locations/api/sword/collection.xml', locals())
        response = HttpResponse(collection_xml)
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response

    elif request.method == 'POST':
        # has the In-Progress header been set?
        if 'HTTP_IN_PROGRESS' in request.META:
            # process creation request, if criteria met
            source_location = request.GET.get('source_location', '')
            relative_path_to_files = request.GET.get('relative_path_to_files', '')
            
            if request.body != '':
                try:
                    temp_filepath = helpers.write_request_body_to_temp_file(request)

                    # parse name and content URLs out of XML
                    try:
                        mets_data = _parse_name_and_content_urls_from_mets_file(temp_filepath)
                    except etree.XMLSyntaxError as e:
                        os.unlink(temp_filepath)
                        mets_data = None

                    if mets_data != None:
                        if mets_data['deposit_name'] == None:
                            return helpers.sword_error_response(request, 400, 'No deposit name found in XML.')
                        if not os.path.isdir(location.full_path()):
                            return helpers.sword_error_response(request, 500, 'Collection path (%s) does not exist: contact an administrator.' % (location.full_path()))

                        # TODO: should get this from author header or provided XML metadata
                        sourceofacquisition = request.META['HTTP_ON_BEHALF_OF'] if 'HTTP_ON_BEHALF_OF' in request.META else None
                        deposit = _create_deposit_directory_and_db_entry(
                            location=location,
                            deposit_name=mets_data['deposit_name'],
                            sourceofacquisition=sourceofacquisition
                        )
                        if deposit is None:
                            return helpers.sword_error_response(request, 500, 'Could not create deposit: contact an administrator.')

                        # move METS file to submission documentation directory
                        object_id = mets_data.get('object_id', 'fedora')
                        helpers.store_mets_data(temp_filepath, deposit, object_id)

                        _spawn_batch_download_and_flag_finalization_if_requested(deposit, request, mets_data)

                        if request.META['HTTP_IN_PROGRESS'] == 'true':
                            return _deposit_receipt_response(request, deposit, 201)
                        else:
                            return _deposit_receipt_response(request, deposit, 200)
                    else:
                        return helpers.sword_error_response(request, 412, 'Error parsing XML')
                except Exception as e:
                    return helpers.sword_error_response(request, 400, traceback.format_exc())
            elif source_location or relative_path_to_files:
                if not source_location or not relative_path_to_files:
                    if not source_location:
                        return helpers.sword_error_response(request, 400, 'relative_path_to_files is set, but source_location is not.')
                    else:
                        return helpers.sword_error_response(request, 400, 'source_location is set, but relative_path_to_files is not.')
                else:
                    result = deposit_from_location_relative_path(source_location, relative_path_to_files, location)
                    if result.get('error', False):
                        return helpers.sword_error_response(request, 500, result['message'])
                    else:
                        return _deposit_receipt_response(request, result['deposit_uuid'], 200)
            else:
                return helpers.sword_error_response(request, 412, 'A request body must be sent when creating a deposit.')
        else:
            return helpers.sword_error_response(request, 412, 'The In-Progress header must be set to either true or false when creating a deposit.')
    else:
        return helpers.sword_error_response(request, 405, 'This endpoint only responds to the GET and POST HTTP methods.')

def deposit_from_location_relative_path(source_location_uuid, relative_path_to_files, location):
    """
    Create and approve deposit using files in an existing location at a relative
    path within the location

    Returns dict combining returned response from the dashboard with the UUID of
    the new deposit, or {'error': True, 'message': <error message>}
    """
    # All parameters must exist, and have useful data
    if not all([source_location_uuid, relative_path_to_files, location]):
        return {
            'error': True,
            'message': 'source_location, relative_path_to_files or the location were empty',
        }

    # a deposit of files stored on the storage server is being done
    source_location = models.Location.objects.get(uuid=source_location_uuid)
    path_to_deposit_files = os.path.join(source_location.full_path(), relative_path_to_files.rstrip('/'))

    deposit = _create_deposit_directory_and_db_entry(
        location,
        deposit_name=os.path.basename(path_to_deposit_files), # replace this with optional name
        source_path=path_to_deposit_files,
    )
    # FIXME move files from source location to deposit path using
    # Space.move_[to|from]_storage_service before finalizing deposit
    result = helpers._finalize_if_not_empty(deposit.uuid)
    result['deposit_uuid'] = deposit.uuid
    return result

def _spawn_batch_download_and_flag_finalization_if_requested(deposit, request, mets_data):
    """
    Spawn a batch download, optionally setting finalization beforehand.

    If HTTP_IN_PROGRESS is set to true, spawn async batch download
    """
    if request.META['HTTP_IN_PROGRESS'] == 'false':
        # Indicate that the deposit is ready for finalization (after all batch
        # downloads have completed)
        deposit.misc_attributes.update({'ready_for_finalization': True})
        deposit.save()

    # create subprocess so content URLs can be downloaded asynchronously
    helpers.spawn_download_task(deposit.uuid, mets_data['objects'])
    helpers.spawn_download_task(deposit.uuid, mets_data['mods'], ['submissionDocumentation', 'mods'])

def _parse_name_and_content_urls_from_mets_file(filepath):
    """
    Parse deposit name and control URLS from a METS XML file

    Returns a dict with the keys 'deposit_name' and 'objects'
    """
    tree = etree.parse(filepath)
    root = tree.getroot()
    deposit_name = root.get('LABEL')
    object_id = root.get('OBJID')
    logging.info('found deposit name in mets: ' + deposit_name)

    # parse XML for content URLs
    objects = []
    mods = []

    expression = "{http://www.loc.gov/METS/}fileSec/" + \
        "{http://www.loc.gov/METS/}fileGrp[@ID='DATASTREAMS']/" + \
        "{http://www.loc.gov/METS/}fileGrp[@ID='{type}']/" + \
        "{http://www.loc.gov/METS/}file/" + \
        "{http://www.loc.gov/METS/}FLocat"

    for type_ in ('OBJ', 'MODS'):
        elements = root.iterfind(expression.replace('{type}', type_))

        if type_ == 'OBJ':
            collection = objects
        elif type_ == 'MODS':
            collection = mods

        for element in elements:
            url = element.get('{http://www.w3.org/1999/xlink}href')
            filename = element.get('{http://www.w3.org/1999/xlink}title')

            # only MD5 checksums currently supported
            checksumtype = element.get('CHECKSUMTYPE')
            checksum = element.get('CHECKSUM')

            if checksum is not None and checksumtype != 'MD5':
                raise Exception('If using CHECKSUM attribute, CHECKSUMTYPE attribute value must be set to MD5 in XML')

            collection.append({
               'object_id': object_id,
               'filename': filename,
               'url': url,
               'checksum': checksum
            })
            logging.info('found url in mets: ' + url)

    return {
        'deposit_name': deposit_name,
        'mods': mods,
        'objects': objects,
        'object_id': object_id
    }

def _create_deposit_directory_and_db_entry(location, deposit_name=None, source_path=None, sourceofacquisition=None):
    """
    Create a new deposit package, optionally copying files to it from a source path.

    Returns the deposit if creation was successful, None if not
    """
    if deposit_name is None:
        deposit_name = 'Untitled'

    # Formulate deposit path using space path and deposit name
    deposit_path = os.path.join(location.full_path(), deposit_name)

    # Pad deposit path, if it already exists, and either copy source data to it or just create it
    deposit_path = helpers.pad_destination_filepath_if_it_already_exists(deposit_path)

    if source_path:
        shutil.copytree(source_path, deposit_path)
    else:
        os.mkdir(deposit_path)
        os.chmod(deposit_path, 02770) # drwxrws---

    # Create SWORD deposit location using deposit name and path
    if os.path.exists(deposit_path):
        deposit = models.Package.objects.create(
            description=deposit_name,
            current_location=location,
            current_path=os.path.basename(deposit_path),
            package_type=models.Package.DEPOSIT,
            status=models.Package.PENDING,
        )
        # TODO: implement this
        if sourceofacquisition:
            deposit.misc_attributes.update(
                {'sourceofacquisition': sourceofacquisition})
        deposit.save()
        return deposit
    return None

def deposit_edit(request, deposit):
    """
    Deposit endpoint: list info, accept new files, finalize or delete deposit.

    Example POST adding files to the deposit:
      curl -v -H "In-Progress: true" --data-binary @mets.xml --request POST http://127.0.0.1:8000/api/v1/file/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/

    Example POST finalization of deposit:
      curl -v -H "In-Progress: false" --request POST http://127.0.0.1:8000/api/v1/file/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/

    Example DELETE of deposit:
      curl -v -XDELETE http://127.0.0.1:8000/api/v1/file/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/
    """
    if isinstance(deposit, basestring):
        try:
            deposit = models.Package.active.get(uuid=deposit)
        except models.Package.DoesNotExist:
            return helpers.sword_error_response(request, 404, 'Deposit location {uuid} does not exist.'.format(uuid=deposit))

    if deposit.has_been_submitted_for_processing():
        return helpers.sword_error_response(request, 400, 'This deposit has already been submitted for processing.')

    if request.method == 'GET':
        edit_iri = request.build_absolute_uri(
            reverse('sword_deposit', kwargs={
                'api_name': 'v1', 'resource_name': 'file', 'uuid': deposit.uuid}))
        entry = {
            'title': deposit.description,
            'url': edit_iri
        }
        response = HttpResponse(render_to_string('locations/api/sword/entry.xml', locals()))
        response['Content-Type'] = 'application/atom+xml'
        return response
    elif request.method == 'POST':
        # If METS XML has been sent to indicate a list of files needing downloading, handle it
        if request.body != '':
            temp_filepath = helpers.write_request_body_to_temp_file(request)
            try:
                mets_data = _parse_name_and_content_urls_from_mets_file(temp_filepath)
            except etree.XMLSyntaxError as e:
                os.unlink(temp_filepath)
                mets_data = None

            if mets_data is not None:
                # move METS file to submission documentation directory
                object_id = mets_data.get('object_id', 'fedora')
                helpers.store_mets_data(temp_filepath, deposit, object_id)

                _spawn_batch_download_and_flag_finalization_if_requested(deposit, request, mets_data)
                return _deposit_receipt_response(request, deposit, 200)
            else:
                return helpers.sword_error_response(request, 412, 'Error parsing XML.')
        else:
            # Attempt to finalize (if requested), otherwise just return deposit receipt
            if 'HTTP_IN_PROGRESS' in request.META and request.META['HTTP_IN_PROGRESS'] == 'false':
                return _finalize_or_mark_for_finalization(request, deposit)
            else:
                return _deposit_receipt_response(request, deposit, 200)
    elif request.method == 'PUT':
        # TODO: implement update deposit
        return HttpResponse(status=204) # No content
    elif request.method == 'DELETE':
        # Delete files
        shutil.rmtree(deposit.full_path())
        # Delete all PackageDownloadTaskFile and PackageDownloadTask for this deposit
        models.PackageDownloadTaskFile.objects.filter(task__package=deposit).delete()
        models.PackageDownloadTask.objects.filter(package=deposit).delete()
        # TODO should this actually delete the Package entry?
        deposit.status = models.Package.DELETED
        deposit.save()
        return HttpResponse(status=204) # No content
    else:
        return helpers.sword_error_response(request, 405, 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.')

def _finalize_or_mark_for_finalization(request, deposit):
    """
    If a request specifies the deposit should be finalized, synchronously finalize
    or, if downloading is incomplete, mark for finalization.

    Returns deposit receipt response or error response
    """
    if 'HTTP_IN_PROGRESS' in request.META and request.META['HTTP_IN_PROGRESS'] == 'false':
        if helpers.deposit_downloading_status(deposit) == models.PackageDownloadTask.COMPLETE:
            helpers.spawn_finalization(deposit.uuid)
            return _deposit_receipt_response(request, deposit, 200)
        else:
            return helpers.sword_error_response(request, 400, 'Downloading not yet complete or errors were encountered.')
    else:
        return helpers.sword_error_response(request, 400, 'The In-Progress header must be set to false when starting deposit processing.')

def deposit_media(request, deposit):
    """
    Deposit media endpoint: list, create, update or delete files

    Example GET of files list:
      curl -v http://127.0.0.1:8000/api/v1/file/149cc29d-6472-4bcf-bee8-f8223bf60580/sword/media/

    Example PUT of file:
      curl -v -H "Content-Disposition: attachment; filename=joke.jpg" --data-binary "@joke.jpg" --request PUT http://127.0.0.1:8000/api/v1/file/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

    Example POST of file:
      curl -v -H "Content-Disposition: attachment; filename=joke.jpg" --data-binary "@joke.jpg" --request POST http://127.0.0.1:8000/api/v1/file/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

    Example POST of METS with file info:
      curl -v -H "Packaging: METS" -H "In-Progress: true" --data-binary @mets.xml --request POST http://127.0.0.1:8000/api/v1/file/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

    Example DELETE of all files:
      curl -v -XDELETE http://127.0.0.1:8000/api/v1/file/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/

    Example DELETE of file:
      curl -v -XDELETE http://127.0.0.1:8000/api/v1/file/9c8b4ac0-0407-4360-a10d-af6c62a48b69/sword/media/?filename=joke.jpg
    """

    if isinstance(deposit, basestring):
        try:
            deposit = models.Package.active.get(uuid=deposit)
        except models.Package.DoesNotExist:
            return helpers.sword_error_response(request, 404, 'Deposit location {uuid} does not exist.'.format(uuid=deposit))

    if deposit.has_been_submitted_for_processing():
        return helpers.sword_error_response(request, 400, 'This deposit has already been submitted for processing.')

    if request.method == 'GET':
        # TODO should this be returned in SWORD XML?
        return HttpResponse(str(os.listdir(deposit.full_path())))
    elif request.method == 'PUT':
        # replace a file in the deposit
        return _handle_adding_to_or_replacing_file_in_deposit(request, deposit, replace_file=True)
    elif request.method == 'POST':
        # Allow async batch upload via METS XML body content
        if 'HTTP_PACKAGING' in request.META and request.META['HTTP_PACKAGING'] == 'METS':
            # If METS XML has been sent to indicate a list of files needing downloading, handle it
            if request.body != '':
                temp_filepath = helpers.write_request_body_to_temp_file(request)
                try:
                    mets_data = _parse_name_and_content_urls_from_mets_file(temp_filepath)
                except etree.XMLSyntaxError as e:
                    os.unlink(temp_filepath)
                    mets_data = None

                if mets_data != None:
                    # move METS file to submission documentation directory
                    object_id = mets_data.get('object_id', 'fedora')
                    helpers.store_mets_data(temp_filepath, deposit, object_id)

                    _spawn_batch_download_and_flag_finalization_if_requested(deposit, request, mets_data)
                    return _deposit_receipt_response(request, deposit, 201)
                else:
                    return helpers.sword_error_response(request, 412, 'Error parsing XML.')
            else:
                return helpers.sword_error_response(request, 400, 'No METS body content sent.')
        else:
            # add a file to the deposit
            return _handle_adding_to_or_replacing_file_in_deposit(request, deposit)
    elif request.method == 'DELETE':
        filename = request.GET.get('filename', '')
        if filename != '':
            # Delete PackageDownloadTaskFile for this filename
            models.PackageDownloadTaskFile.objects.filter(task__package=deposit).filter(filename=filename).delete()
            # Delete empty PackageDownloadTasks for this deposit
            models.PackageDownloadTask.objects.filter(package=deposit).filter(download_file_set=None).delete()
            # Delete file
            file_path = os.path.join(deposit.full_path(), filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                return HttpResponse(status=204) # No content
            else:
                return helpers.sword_error_response(request, 404, 'The path to this file (%s) does not exist.' % (file_path))
        else:
            # Delete all PackageDownloadTaskFile and PackageDownloadTask for this deposit
            models.PackageDownloadTaskFile.objects.filter(task__package=deposit).delete()
            models.PackageDownloadTask.objects.filter(package=deposit).delete()
            # Delete all files
            for filename in os.listdir(deposit.full_path()):
                filepath = os.path.join(deposit.full_path(), filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)

            return HttpResponse(status=204) # No content
    else:
        return helpers.sword_error_response(request, 405, 'This endpoint only responds to the GET, POST, PUT, and DELETE HTTP methods.')

def deposit_state(request, deposit):
    """
    Deposit state endpoint: return status of this deposit

    Example GET of state:
      curl -v http://localhost:8000/api/v1/location/96606387-cc70-4b09-b422-a7220606488d/sword/state/
    """
    if isinstance(deposit, basestring):
        try:
            deposit = models.Package.active.get(uuid=deposit)
        except models.Package.DoesNotExist:
            return helpers.sword_error_response(request, 404, 'Deposit location {uuid} does not exist.'.format(uuid=deposit))

    if request.method == 'GET':
        status = helpers.deposit_downloading_status(deposit)
        state_term = status
        state_description = 'Deposit initiation: ' + status

        # if deposit hasn't been finalized and last finalization attempt
        # failed, note failed finalization

        if deposit.misc_attributes.get('finalization_attempt_failed', None) and deposit.misc_attributes.get('deposit_completion_time', None) is None:
            state_description += ' (last finalization attempt failed)'

        # get status of download tasks, if any
        tasks = helpers.deposit_download_tasks(deposit)

        # create atom representation of download tasks
        entries = []

        for task in tasks:
            task_files = models.PackageDownloadTaskFile.objects.filter(task=task)
            for task_file in task_files:
                entries.append({
                    'title': task_file.filename,
                    'url': task_file.url,
                    'summary': task_file.downloading_status()
                })

        response = HttpResponse(render_to_string('locations/api/sword/state.xml', locals()))
        response['Content-Type'] = 'application/atom+xml;type=feed'
        return response
    else:
        return helpers.sword_error_response(request, 405, 'This endpoint only responds to the GET HTTP method.')

def _handle_adding_to_or_replacing_file_in_deposit(request, deposit, replace_file=False):
    """
    Parse a destination filename from an HTTP Content-Disposition header and
    either add or replace it

    Returns a response with an HTTP status code indicating whether creation (201)
    or updating (204) has occurred or an error response
    """
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
                    return helpers.sword_error_response(request, 400, 'File does not exist.')
            else:
                # if adding a file, the file must not already exist
                if os.path.exists(file_path):
                    return helpers.sword_error_response(request, 400, 'File already exists.')
                else:
                    return _handle_upload_request_with_potential_md5_checksum(
                        request,
                        file_path,
                        201
                    )
        else:
            return helpers.sword_error_response(request, 400, 'No filename found in Content-disposition header.')
    else:
        return helpers.sword_error_response(request, 400, 'Content-disposition must be set in request header.')

def _handle_upload_request_with_potential_md5_checksum(request, file_path, success_status_code):
    """
    Write the HTTP request body to a file and, if the HTTP Content-MD5 header is
    set, make sure the destination file has the expected checkcum

    Returns a response (with a specified HTTP status code) or an error response
    if a checksum has been provided but the destination file's is different
    """
    temp_filepath = helpers.write_request_body_to_temp_file(request)
    if 'HTTP_CONTENT_MD5' in request.META:
        md5sum = helpers.get_file_md5_checksum(temp_filepath)
        if request.META['HTTP_CONTENT_MD5'] != md5sum:
            os.remove(temp_filepath)
            return helpers.sword_error_response(request, 400, 'MD5 checksum of uploaded file ({uploaded_md5sum}) does not match checksum provided in header ({header_md5sum}).'.format(
                uploaded_md5sum=md5sum, header_md5sum=request.META['HTTP_CONTENT_MD5']))
        else:
            shutil.copyfile(temp_filepath, file_path)
            os.remove(temp_filepath)
            return HttpResponse(status=success_status_code)
    else:
        shutil.copyfile(temp_filepath, file_path)
        os.remove(temp_filepath)
        return HttpResponse(status=success_status_code)

def _deposit_receipt_response(request, deposit, status_code):
    """
    Generate SWORD 2.0 deposit receipt response
    """
    # Deposit needed for deposit receipt template
    if isinstance(deposit, basestring):
        deposit = models.Package.objects.get(uuid=deposit)
    # TODO: fix minor issues with template
    media_iri = request.build_absolute_uri(
        reverse('sword_deposit_media', kwargs={'api_name': 'v1',
            'resource_name': 'file', 'uuid': deposit.uuid}))
    edit_iri = request.build_absolute_uri(
        reverse('sword_deposit', kwargs={'api_name': 'v1',
            'resource_name': 'file', 'uuid': deposit.uuid}))
    state_iri = request.build_absolute_uri(
        reverse('sword_deposit_state', kwargs={'api_name': 'v1',
            'resource_name': 'file', 'uuid': deposit.uuid}))
    location = reverse('sword_deposit', kwargs={'api_name': 'v1',
            'resource_name': 'file', 'uuid': deposit.uuid})
    current_datetime = timezone.now()
    receipt_xml = render_to_string('locations/api/sword/deposit_receipt.xml', locals())

    response = HttpResponse(receipt_xml, mimetype='text/xml', status=status_code)
    response['Location'] = location
    return response
