# This file contains the base models that individual versioned models
# are based on. They shouldn't be directly used with Api objects.

# stdlib, alphabetical
import json
import logging
import os
import subprocess
import tempfile
import urllib

# Core Django, alphabetical
from django.conf.urls import url
from django.forms.models import model_to_dict

# Third party dependencies, alphabetical
from tastypie.authentication import (BasicAuthentication, ApiKeyAuthentication,
    MultiAuthentication, Authentication)
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie import fields
from tastypie import http
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation
from tastypie.utils import trailing_slash

# This project, alphabetical
from common import utils

from ..models import (Event, Package, Location, Space, Pipeline)
from ..forms import LocationForm, SpaceForm
from ..constants import PROTOCOL

LOGGER = logging.getLogger(__name__)
logging.basicConfig(filename="/tmp/storage_service.log",
    level=logging.INFO)

# FIXME ModelResources with ForeignKeys to another model don't work with
# validation = CleanedDataFormValidation  On creation, it errors with:
# "Select a valid choice. That choice is not one of the available choices."
# This is because the ModelResource accepts a URI, but does not convert it to a
# primary key (in our case, UUID) before passing it to Django.
# See https://github.com/toastdriven/django-tastypie/issues/152 for details


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

        fields = ['uuid', 'description']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'description': ALL,
            'uuid': ALL,
        }

    def obj_create(self, bundle, **kwargs):
        bundle = super(PipelineResource, self).obj_create(bundle, **kwargs)
        bundle.obj.enabled = not utils.get_setting('pipelines_disabled', False)
        create_default_locations = bundle.data.get('create_default_locations', False)
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

    def browse(self, request, **kwargs):
        """ Returns all of the entries in a space, optionally at a subpath.

        Returns a dict with
            {'entries': [list of entries in the directory],
             'directories': [list of directories in the directory]}
        Directories is a subset of entries, all are just the name.

        If a path=<path> parameter is provided, will look in that path inside
        the Space. """
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)
        path = request.GET.get('path', '')
        space = Space.objects.get(uuid=kwargs['uuid'])
        path = os.path.join(space.path, path)

        objects = self.get_objects(space, path)

        self.log_throttled_access(request)
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
        ]

    def decode_path(self, path):
        return path

    def get_objects(self, space, path):
        message = 'This method should be accessed via a versioned subclass'
        raise NotImplementedError(message)

    def browse(self, request, **kwargs):
        """ Returns all of the entries in a location, optionally at a subpath.

        Returns a dict with
            {'entries': [list of entries in the directory],
             'directories': [list of directories in the directory]}
        Directories is a subset of entries, all are just the name.

        If a path=<path> parameter is provided, will look in that path inside
        the Location. """
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)
        path = request.GET.get('path', '')
        path = self.decode_path(path)
        location = Location.objects.get(uuid=kwargs['uuid'])
        path = os.path.join(str(location.full_path()), path)

        objects = self.get_objects(location.space, path)

        self.log_throttled_access(request)
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
            raise NotFound("The URL provided '%s' was not a link to a valid Location." % origin_uri)

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
            'path': ALL,
            'uuid': ALL,
            'status': ALL
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/delete_aip%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('delete_aip_request'), name="delete_aip_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/extract_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('extract_file_request'), name="extract_file_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/download%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('download_request'), name="download_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/pointer_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('pointer_file_request'), name="pointer_file_request"),
        ]

    def obj_create(self, bundle, **kwargs):
        bundle = super(PackageResource, self).obj_create(bundle, **kwargs)
        # IDEA add custom endpoints, instead of storing all AIPS that come in?
        if bundle.obj.package_type in (Package.AIP, Package.AIC):
            origin_location_uri = bundle.data.get('origin_location', False)
            origin_location = self.origin_location.build_related_resource(origin_location_uri, bundle.request).obj
            origin_path = bundle.data.get('origin_path', False)
            bundle.obj.store_aip(origin_location, origin_path)
        return bundle

    def delete_aip_request(self, request, **kwargs):
        # Tastypie checks
        self.method_check(request, allowed=['post'])
        self.is_authenticated(request)
        self.throttle_check(request)

        # Load request from body, check it has all the keys we need
        request_info = json.loads(request.body)
        if not all(k in request_info for k in
                ('event_reason', 'pipeline', 'user_id', 'user_email')):
            # Don't have enough information to make the request - return error
            return http.HttpBadRequest()

        # Create the Event for package deletion request
        package = Package.objects.get(uuid=kwargs['uuid'])
        if package.package_type not in Package.PACKAGE_TYPE_DELETABLE:
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
        else:
            response = {
                'error_message': 'A deletion request already exists for this AIP.'
            }
            status_code = 200

        self.log_throttled_access(request)
        response_json = json.dumps(response)
        return http.HttpResponse(status=status_code, content=response_json,
            mimetype='application/json')

    def extract_file_request(self, request, **kwargs):
        """
        Returns a single file from the Package, extracting if necessary.
        """
        relative_path_to_file = request.GET.get('relative_path_to_file')
        relative_path_to_file = urllib.unquote(relative_path_to_file)
        temp_dir = extracted_file_path = ''

        # Tastypie checks
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        # Get Package details
        package = Package.objects.get(uuid=kwargs['uuid'])
        full_path = package.full_path()

        local_path = os.path.join(full_path, relative_path_to_file)
        if os.path.exists(local_path):
            # Local file exists - return that
            extracted_file_path = local_path
        elif package.package_type in Package.PACKAGE_TYPE_EXTRACTABLE:
            # If file doesn't exist, try to extract it
            (extracted_file_path, temp_dir) = package.extract_file(relative_path_to_file)

        response = utils.download_file_stream(extracted_file_path, temp_dir)

        self.log_throttled_access(request)
        return response

    def download_request(self, request, **kwargs):
        """
        Returns the entire Package to be downloaded.
        """
        # Tastypie checks
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        # Get AIP details
        package = Package.objects.get(uuid=kwargs['uuid'])
        if package.package_type not in Package.PACKAGE_TYPE_EXTRACTABLE:
            # Can only return packages that are a single file
            # TODO Update to zip up a transfer before returning it?
            return http.HttpMethodNotAllowed()

        full_path = package.full_path()

        response = utils.download_file_stream(full_path)

        self.log_throttled_access(request)
        return response

    def pointer_file_request(self, request, **kwargs):
        # Tastypie checks
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)

        # Get AIP details
        package = Package.objects.get(uuid=kwargs['uuid'])
        pointer_path = package.full_pointer_file_path()
        response = utils.download_file_stream(pointer_path)

        self.log_throttled_access(request)

        return response
