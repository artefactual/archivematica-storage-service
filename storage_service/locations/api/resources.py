# This file contains the base models that individual versioned models
# are based on. They shouldn't be directly used with Api objects.

# stdlib, alphabetical
import json
import logging
import os
import shutil
import urllib

# Core Django, alphabetical
from django.conf import settings
from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.forms.models import model_to_dict

# Third party dependencies, alphabetical
from annoying.functions import get_object_or_None
import bagit
from tastypie.authentication import (BasicAuthentication, ApiKeyAuthentication,
    MultiAuthentication, Authentication)
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie import fields
from tastypie import http
from tastypie.exceptions import UnsupportedFormat
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation
from tastypie.utils import trailing_slash

# This project, alphabetical
from common import utils
from locations.api.sword import views as sword_views

from ..models import (Callback, CallbackError, Event, File, Package, Location, Space, Pipeline, StorageException)
from ..forms import LocationForm, SpaceForm
from ..constants import PROTOCOL
from locations import signals

LOGGER = logging.getLogger(__name__)

# FIXME ModelResources with ForeignKeys to another model don't work with
# validation = CleanedDataFormValidation  On creation, it errors with:
# "Select a valid choice. That choice is not one of the available choices."
# This is because the ModelResource accepts a URI, but does not convert it to a
# primary key (in our case, UUID) before passing it to Django.
# See https://github.com/toastdriven/django-tastypie/issues/152 for details

def _custom_endpoint(expected_methods=['get'], required_fields=[]):
    """
    Decorator for custom endpoints that handles boilerplate code.

    Checks if method allowed, authenticated, deserializes and can require fields
    in the body.

    Custom endpoint must accept request and bundle.
    """
    def decorator(func):
        """ The decorator applied to the endpoint """
        def wrapper(resource, request, **kwargs):
            """ Wrapper for custom endpoints with boilerplate code. """
            # Tastypie API checks
            resource.method_check(request, allowed=expected_methods)
            resource.is_authenticated(request)
            resource.throttle_check(request)

            # Get object
            try:
                obj = resource._meta.queryset.get(uuid=kwargs['uuid'])
            except ObjectDoesNotExist:
                return http.HttpNotFound("Resource with UUID {} does not exist".format(kwargs['uuid']))
            except MultipleObjectsReturned:
                return http.HttpMultipleChoices("More than one resource is found at this URI.")

            # Get body content
            try:
                deserialized = resource.deserialize(request, request.body, format=request.META.get('CONTENT_TYPE', 'application/json'))
                deserialized = resource.alter_deserialized_detail_data(request, deserialized)
            except Exception:
                # Trouble decoding request body - may not actually exist
                deserialized = []

            # Check required fields, if any
            if not all(k in deserialized for k in required_fields):
                # Don't have enough information to make the request - return error
                return http.HttpBadRequest('All of these fields must be provided: {}'.format(', '.join(required_fields)))

            # Build bundle and return it
            bundle = resource.build_bundle(obj=obj, data=deserialized, request=request)
            bundle = resource.alter_detail_data_to_serialize(request, bundle)

            # Call the decorated method
            result = func(resource, request, bundle, **kwargs)
            resource.log_throttled_access(request)
            return result
        return wrapper
    return decorator


class PipelineResource(ModelResource):
    # Attributes used for POST, exclude from GET
    create_default_locations = fields.BooleanField(use_in=lambda x: False)
    shared_path = fields.CharField(use_in=lambda x: False)

    class Meta:
        queryset = Pipeline.active.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=PipelineForm)
        resource_name = 'pipeline'

        fields = ['uuid', 'description', 'remote_name', 'api_key', 'api_username']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'description': ALL,
            'uuid': ALL,
        }

    def dehydrate(self, bundle):
        # Don't return API username or key
        del bundle.data['api_username']
        del bundle.data['api_key']
        return bundle

    def obj_create(self, bundle, **kwargs):
        bundle = super(PipelineResource, self).obj_create(bundle, **kwargs)
        bundle.obj.enabled = not utils.get_setting('pipelines_disabled', False)
        create_default_locations = bundle.data.get('create_default_locations', False)
        # Try to guess Pipeline's IP, if doing default setup
        if create_default_locations:
            ip = bundle.request.META.get('REMOTE_ADDR') or None
            bundle.obj.remote_name = ip
        shared_path = bundle.data.get('shared_path', None)
        bundle.obj.save(create_default_locations, shared_path)
        return bundle


class SpaceResource(ModelResource):
    class Meta:
        queryset = Space.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        validation = CleanedDataFormValidation(form_class=SpaceForm)
        resource_name = 'space'

        fields = ['access_protocol', 'last_verified', 'location_set', 'path',
            'size', 'used', 'uuid', 'verified']
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'access_protocol': ALL,
            'path': ALL,
            'size': ALL,
            'used': ALL,
            'uuid': ALL,
            'verified': ALL,
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/browse%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('browse'), name="browse"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/collection%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_collection'), name="sword_collection")
        ]

    # Is there a better place to add protocol-specific space info?
    # alter_detail_data_to_serialize
    # alter_deserialized_detail_data

    def dehydrate(self, bundle):
        """ Add protocol specific fields to an entry. """
        bundle = super(SpaceResource, self).dehydrate(bundle)
        access_protocol = bundle.obj.access_protocol
        model = PROTOCOL[access_protocol]['model']

        try:
            space = model.objects.get(space=bundle.obj.uuid)
        except model.DoesNotExist:
            print "Item doesn't exist :("
            # TODO this should assert later once creation/deletion stuff works
        else:
            keep_fields = PROTOCOL[access_protocol]['fields']
            added_fields = model_to_dict(space, keep_fields)
            bundle.data.update(added_fields)

        return bundle

    def obj_create(self, bundle, **kwargs):
        """ Creates protocol specific class when creating a Space. """
        # TODO How to move this to the model?
        # Make dict of fields in model and values from bundle.data
        access_protocol = bundle.data['access_protocol']
        keep_fields = PROTOCOL[access_protocol]['fields']
        fields_dict = { key: bundle.data[key] for key in keep_fields }

        bundle = super(SpaceResource, self).obj_create(bundle, **kwargs)

        model = PROTOCOL[access_protocol]['model']
        obj = model.objects.create(space=bundle.obj, **fields_dict)
        obj.save()
        return bundle

    def get_objects(self, space, path):
        message = 'This method should be accessed via a versioned subclass'
        raise NotImplementedError(message)

    @_custom_endpoint(expected_methods=['get'])
    def browse(self, request, bundle, **kwargs):
        """ Returns all of the entries in a space, optionally at a subpath.

        Returns a dict with
            {'entries': [list of entries in the directory],
             'directories': [list of directories in the directory]}
        Directories is a subset of entries, all are just the name.

        If a path=<path> parameter is provided, will look in that path inside
        the Space. """

        space = bundle.obj
        path = request.GET.get('path', '')
        if not path.startswith(space.path):
            path = os.path.join(space.path, path)

        objects = self.get_objects(space, path)

        return self.create_response(request, objects)


class LocationResource(ModelResource):
    space = fields.ForeignKey(SpaceResource, 'space')
    path = fields.CharField(attribute='full_path', readonly=True)
    description = fields.CharField(attribute='get_description', readonly=True)
    pipeline = fields.ToManyField(PipelineResource, 'pipeline')

    class Meta:
        queryset = Location.active.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=LocationForm)
        resource_name = 'location'

        fields = ['enabled', 'relative_path', 'purpose', 'quota', 'used', 'uuid']
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get', 'post']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'relative_path': ALL,
            'pipeline': ALL_WITH_RELATIONS,
            'purpose': ALL,
            'quota': ALL,
            'space': ALL_WITH_RELATIONS,
            'used': ALL,
            'uuid': ALL,
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/browse%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('browse'), name="browse"),
            # FEDORA/SWORD2 endpoints
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/collection%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_collection'), name="sword_collection"),

        ]

    def decode_path(self, path):
        return path

    def get_objects(self, space, path):
        message = 'This method should be accessed via a versioned subclass'
        raise NotImplementedError(message)

    @_custom_endpoint(expected_methods=['get'])
    def browse(self, request, bundle, **kwargs):
        """ Returns all of the entries in a location, optionally at a subpath.

        Returns a dict with
            {'entries': [list of entries in the directory],
             'directories': [list of directories in the directory]}
        Directories is a subset of entries, all are just the name.

        If a path=<path> parameter is provided, will look in that path inside
        the Location. """

        location = bundle.obj
        path = request.GET.get('path', '')
        path = self.decode_path(path)
        if not path.startswith(location.full_path):
            path = os.path.join(location.full_path, path)

        objects = self.get_objects(location.space, path)

        return self.create_response(request, objects)

    def post_detail(self, request, *args, **kwargs):
        """ Moves files to this Location.

        Intended for use with creating Transfers, SIPs, etc and other cases
        where files need to be moved but not tracked by the storage service.

        POST body should contain a dict with elements:
        origin_location: URI of the Location the files should be moved from
        pipeline: URI of the Pipeline both Locations belong to
        files: List of dicts containing 'source' and 'destination', paths
            relative to their Location of the files to be moved.
        """
        # Not right HTTP verb?  PUT is taken

        data = self.deserialize(request, request.body)
        data = self.alter_deserialized_detail_data(request, data)

        # Get the object for this endpoint
        try:
            destination_location = Location.objects.get(uuid=kwargs['uuid'])
        except Location.DoesNotExist:
            return http.HttpNotFound()

        # Check for require fields
        required_fields = ['origin_location', 'pipeline', 'files']
        if not all((k in data) for k in required_fields):
            # Don't have enough information to make the request - return error
            return http.HttpBadRequest

        # Get the destination Location
        origin_uri = data['origin_location']
        try:
            # splitting origin_uri on / results in:
            # ['', 'api', 'v1', '<resource_name>', '<uuid>', '']
            origin_uuid = origin_uri.split('/')[4]
            origin_location = Location.objects.get(uuid=origin_uuid)
        except (IndexError, Location.DoesNotExist):
            raise http.HttpNotFound("The URL provided '%s' was not a link to a valid Location." % origin_uri)

        # For each file in files, call move to/from
        origin_space = origin_location.space
        destination_space = destination_location.space
        files = data['files']
        # TODO make these move async so the SS can continue to respond while
        # moving large files
        for sip_file in files:
            source_path = sip_file.get('source', None)
            destination_path = sip_file.get('destination', None)
            if all([source_path, destination_path]):
                # make path relative to the location
                source_path = os.path.join(
                    origin_location.relative_path, source_path)
                destination_path = os.path.join(
                    destination_location.relative_path, destination_path)
                origin_space.move_to_storage_service(
                    source_path=source_path,
                    destination_path=destination_path,
                    destination_space=destination_space,
                )
                origin_space.post_move_to_storage_service()
                destination_space.move_from_storage_service(
                    source_path=destination_path,
                    destination_path=destination_path,
                )
                destination_space.post_move_from_storage_service()

            else:
                return http.HttpBadRequest

        response = {'error': None,
                    'message': 'Files moved successfully'}
        return self.create_response(request, response)

    def sword_collection(self, request, **kwargs):
        location = get_object_or_None(Location, uuid=kwargs['uuid'])
        if location and (location.purpose != Location.SWORD_DEPOSIT or location.space.access_protocol != Space.FEDORA):
            return http.HttpBadRequest('This is not a SWORD server space.')
        self.log_throttled_access(request)
        return sword_views.collection(request, location or kwargs['uuid'])


class PackageResource(ModelResource):
    """ Resource for managing Packages.

    List (api/v1/file/) supports:
    GET: List of files
    POST: Create new Package

    Detail (api/v1/file/<uuid>/) supports:
    GET: Get details on a specific file

    Download package (/api/v1/file/<uuid>/download/) supports:
    GET: Get package as download

    Extract file (/api/v1/file/<uuid>/extract_file/) supports:
    GET: Extract file from package (param "relative_path_to_file" specifies which file)

    api/v1/file/<uuid>/delete_aip/ supports:
    POST: Create a delete request for that AIP.

    Validate fixity (api/v1/file/<uuid>/check_fixity/) supports:
    GET: Scan package for fixity
    """
    origin_pipeline = fields.ForeignKey(PipelineResource, 'origin_pipeline')
    origin_location = fields.ForeignKey(LocationResource, None, use_in=lambda x: False)
    origin_path = fields.CharField(use_in=lambda x: False)
    current_location = fields.ForeignKey(LocationResource, 'current_location')

    current_full_path = fields.CharField(attribute='full_path', readonly=True)

    class Meta:
        queryset = Package.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=PackageForm)
        #
        # Note that this resource is exposed as 'file' to the API for
        # compatibility because the resource itself was originally under
        # that name.
        resource_name = 'file'

        fields = ['current_path', 'package_type', 'size', 'status', 'uuid']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'location': ALL_WITH_RELATIONS,
            'package_type': ALL,
            'path': ALL,
            'uuid': ALL,
            'status': ALL,
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/delete_aip%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('delete_aip_request'), name="delete_aip_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/extract_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('extract_file_request'), name="extract_file_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/download/(?P<chunk_number>\d+)%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('download_request'), name="download_lockss"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/download%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('download_request'), name="download_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/pointer_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('pointer_file_request'), name="pointer_file_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/check_fixity%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('check_fixity_request'), name="check_fixity_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/send_callback/post_store%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('aip_store_callback_request'), name="aip_store_callback_request"),

            # FEDORA/SWORD2 endpoints
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit'), name="sword_deposit"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/media%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit_media'), name="sword_deposit_media"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/state%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit_state'), name="sword_deposit_state"),
        ]

    def obj_create(self, bundle, **kwargs):
        bundle = super(PackageResource, self).obj_create(bundle, **kwargs)
        # IDEA add custom endpoints, instead of storing all AIPS that come in?
        origin_location_uri = bundle.data.get('origin_location', False)
        origin_location = self.origin_location.build_related_resource(origin_location_uri, bundle.request).obj
        origin_path = bundle.data.get('origin_path', False)
        if bundle.obj.package_type in (Package.AIP, Package.AIC, Package.DIP) and bundle.obj.current_location.purpose in (Location.AIP_STORAGE, Location.DIP_STORAGE):
            # Store AIP/AIC
            bundle.obj.store_aip(origin_location, origin_path)
        elif bundle.obj.package_type in (Package.TRANSFER) and bundle.obj.current_location.purpose in (Location.BACKLOG):
            # Move transfer to backlog
            bundle.obj.backlog_transfer(origin_location, origin_path)
        return bundle

    @_custom_endpoint(expected_methods=['post'],
        required_fields=('event_reason', 'pipeline', 'user_id', 'user_email'))
    def delete_aip_request(self, request, bundle, **kwargs):
        request_info = bundle.data
        package = bundle.obj
        if package.package_type not in Package.PACKAGE_TYPE_CAN_DELETE:
            # Can only request deletion on AIPs
            return http.HttpMethodNotAllowed()

        pipeline = Pipeline.objects.get(uuid=request_info['pipeline'])

        # See if an event already exists
        existing_requests = Event.objects.filter(package=package,
            event_type=Event.DELETE, status=Event.SUBMITTED).count()
        if existing_requests < 1:
            delete_request = Event(package=package, event_type=Event.DELETE,
                status=Event.SUBMITTED, event_reason=request_info['event_reason'],
                pipeline=pipeline, user_id=request_info['user_id'],
                user_email=request_info['user_email'], store_data=package.status)
            delete_request.save()

            # Update package status
            package.status = Package.DEL_REQ
            package.save()

            response = {
                'message': 'Delete request created successfully.'
            }

            response_json = json.dumps(response)
            status_code = 202

            # This isn't configured by default
            site_url = getattr(settings, "SITE_BASE_URL", None)
            signals.deletion_request.send(sender=self, url=site_url,
                uuid=package.uuid, location=package.full_path)
        else:
            response = {
                'message': 'A deletion request already exists for this AIP.'
            }
            status_code = 200

        self.log_throttled_access(request)
        response_json = json.dumps(response)
        return http.HttpResponse(status=status_code, content=response_json,
            mimetype='application/json')

    @_custom_endpoint(expected_methods=['get'])
    def extract_file_request(self, request, bundle, **kwargs):
        """
        Returns a single file from the Package, extracting if necessary.
        """
        relative_path_to_file = request.GET.get('relative_path_to_file')
        relative_path_to_file = urllib.unquote(relative_path_to_file)
        temp_dir = extracted_file_path = ''

        # Get Package details
        package = bundle.obj

        # If local file exists - return that
        if not package.is_compressed:
            full_path = package.fetch_local_path()
            # The basename of the AIP may be included with the request, because
            # all AIPs contain a base directory. That directory may already be
            # inside the full path though, so remove the basename only if the
            # relative path begins with it.
            basename = os.path.join(os.path.basename(full_path), '')
            if relative_path_to_file.startswith(basename):
                relative_path_to_file = relative_path_to_file.replace(basename, '', 1)
            extracted_file_path = os.path.join(full_path, relative_path_to_file)
            if not os.path.exists(extracted_file_path):
                return http.HttpResponse(status=404,
                    content="Requested file, {}, not found in AIP".format(relative_path_to_file))
        elif package.package_type in Package.PACKAGE_TYPE_CAN_EXTRACT:
            # If file doesn't exist, try to extract it
            (extracted_file_path, temp_dir) = package.extract_file(relative_path_to_file)
        else:
            # If the package is compressed and we can't extract it,
            return http.HttpResponse(status=501,
                content="Unable to extract package of type: {}".format(package.package_type))

        response = utils.download_file_stream(extracted_file_path, temp_dir)

        return response

    @_custom_endpoint(expected_methods=['get'])
    def download_request(self, request, bundle, **kwargs):
        """
        Returns the entire Package to be downloaded.
        """
        # Get AIP details
        package = bundle.obj

        lockss_au_number = kwargs.get('chunk_number')
        try:
            temp_dir = None
            full_path = package.get_download_path(lockss_au_number)
        except StorageException:
            full_path, temp_dir = package.compress_package(Package.COMPRESSION_TAR)

        response = utils.download_file_stream(full_path)

        return response

    @_custom_endpoint(expected_methods=['get'])
    def pointer_file_request(self, request, bundle, **kwargs):
        # Get AIP details
        pointer_path = bundle.obj.full_pointer_file_path
        if not pointer_path:
            response = http.HttpNotFound("Resource with UUID {} does not have a pointer file".format(bundle.obj.uuid))
        else:
            response = utils.download_file_stream(pointer_path)
        return response

    @_custom_endpoint(expected_methods=['get'])
    def check_fixity_request(self, request, bundle, **kwargs):
        success, failures, message = bundle.obj.check_fixity()

        response = {
            "success": success,
            "message": message,
            "failures": {
                "files": {
                    "missing": [],
                    "changed": [],
                    "untracked": [],
                }
            }
        }

        for failure in failures:
            if isinstance(failure, bagit.FileMissing):
                info = {
                    "path": failure.path,
                    "message": str(failure)
                }
                response["failures"]["files"]["missing"].append(info)
            if isinstance(failure, bagit.ChecksumMismatch):
                info = {
                    "path": failure.path,
                    "expected": failure.expected,
                    "actual": failure.found,
                    "hash_type": failure.algorithm,
                    "message": str(failure),
                }
                response["failures"]["files"]["changed"].append(info)
            if isinstance(failure, bagit.UnexpectedFile):
                info = {
                    "path": failure.path,
                    "message": str(failure)
                }
                response["failures"]["files"]["untracked"].append(info)

        report = json.dumps(response)
        if not success:
            signals.failed_fixity_check.send(sender=self,
                uuid=bundle.obj.uuid, location=bundle.obj.full_path,
                report=report)

        return http.HttpResponse(
            report,
            mimetype="application/json"
        )
        return response

    @_custom_endpoint(expected_methods=['get'])
    def aip_store_callback_request(self, request, bundle, **kwargs):
        package = bundle.obj

        callbacks = Callback.objects.filter(event="post_store")
        if len(callbacks) == 0:
            return http.HttpNoContent()

        fail = 0

        if package.is_compressed:
            # Don't extract the entire AIP, which could take forever;
            # instead, just extract bagit.txt and manifest-sha512.txt,
            # which is enough to get bag.entries with the
            # precalculated sha512 checksums
            try:
                basedir = package.get_base_directory()
            # Currently we only support this for local packages.
            except NotImplementedError:
                return http.HttpNoContent()

            _, tmpdir = package.extract_file(os.path.join(basedir, 'bagit.txt'))
            package.extract_file(os.path.join(basedir, 'manifest-sha512.txt'),
                extract_path=tmpdir)

            package_dir = os.path.join(tmpdir, basedir)
        else:
            package_dir = package.full_path()
            tmpdir = None

        safe_files = ('bag-info.txt', 'manifest-sha512.txt', 'bagit.txt')

        bag = bagit.Bag(package_dir)
        for f, checksums in bag.entries.iteritems():
            try:
                cksum = checksums['sha512']
            except KeyError:
                # These files do not typically have an sha512 hash, so it's
                # fine for these to be missing that key; every other file should.
                if f not in safe_files:
                    LOGGER.warning("Post-store callback: sha512 missing for file %s", f)
                continue

            files = File.objects.filter(checksum=cksum, stored=False)
            if len(files) > 1:
                LOGGER.warning("Multiple File entries found for sha512 {}".format(cksum))

            for file_ in files:
                for callback in callbacks:
                    uri = callback.uri.replace('<source_id>', file_.source_id)
                    try:
                        callback.execute(uri)
                        file_.stored = True
                        file_.save()
                    except CallbackError:
                        fail += 1

        if tmpdir is not None:
            shutil.rmtree(tmpdir)

        if fail > 0:
            response = {
                "message": "Failed to POST {} responses to callback URI".format(fail),
                "failure_count": fail,
                "callback_uris": [c.uri for c in callbacks]
            }
            return http.ApplicationError(
                json.dumps(response),
                mimetype="application/json"
            )
        else:
            return http.HttpNoContent()

    def sword_deposit(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest('This is not a SWORD deposit location.')
        self.log_throttled_access(request)
        return sword_views.deposit_edit(request, package or kwargs['uuid'])

    def sword_deposit_media(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest('This is not a SWORD deposit location.')
        self.log_throttled_access(request)
        return sword_views.deposit_media(request, package or kwargs['uuid'])

    def sword_deposit_state(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest('This is not a SWORD deposit location.')
        self.log_throttled_access(request)
        return sword_views.deposit_state(request, package or kwargs['uuid'])
