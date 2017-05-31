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
from django.utils.translation import ugettext as _

# Third party dependencies, alphabetical
from annoying.functions import get_object_or_None
import bagit
from tastypie.authentication import BasicAuthentication, ApiKeyAuthentication, MultiAuthentication, SessionAuthentication
from tastypie.authorization import DjangoAuthorization
import tastypie.exceptions
from tastypie import fields
from tastypie import http
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation
from tastypie.utils import trailing_slash

# This project, alphabetical
from common import utils
from locations.api.sword import views as sword_views

from ..models import (Callback, CallbackError, Event, File, Package, Location, Space, Pipeline, StorageException)
from ..forms import SpaceForm
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
                return http.HttpNotFound(_('Resource with UUID %(uuid)s does not exist') % {'uuid': kwargs['uuid']})
            except MultipleObjectsReturned:
                return http.HttpMultipleChoices(_("More than one resource is found at this URI."))

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
                return http.HttpBadRequest(_('All of these fields must be provided: %(fields)s') % {'fields': ', '.join(required_fields)})

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
        authentication = MultiAuthentication(BasicAuthentication(), ApiKeyAuthentication(), SessionAuthentication())
        authorization = DjangoAuthorization()
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
        authentication = MultiAuthentication(BasicAuthentication(), ApiKeyAuthentication(), SessionAuthentication())
        authorization = DjangoAuthorization()
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
            LOGGER.error('Space matching UUID %s does not exist', bundle.obj.uuid)
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
        fields_dict = {key: bundle.data[key] for key in keep_fields}

        bundle = super(SpaceResource, self).obj_create(bundle, **kwargs)

        model = PROTOCOL[access_protocol]['model']
        obj = model.objects.create(space=bundle.obj, **fields_dict)
        obj.save()
        return bundle

    def get_objects(self, space, path):
        message = _('This method should be accessed via a versioned subclass')
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
        authentication = MultiAuthentication(BasicAuthentication(), ApiKeyAuthentication(), SessionAuthentication())
        authorization = DjangoAuthorization()
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
        message = _('This method should be accessed via a versioned subclass')
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
        location_path = location.full_path
        if isinstance(location_path, unicode):
            location_path = location_path.encode('utf8')
        if not path.startswith(location_path):
            path = os.path.join(location_path, path)

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
            destination_location = Location.active.get(uuid=kwargs['uuid'])
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
            origin_location = Location.active.get(uuid=origin_uuid)
        except (IndexError, Location.DoesNotExist):
            return http.HttpNotFound(
                _("The URL provided '%(url)s' was not a link to a valid Location.") %
                {'url': origin_uri})

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
                    package=None,
                )
                destination_space.post_move_from_storage_service(
                    destination_path, destination_path)

            else:
                return http.HttpBadRequest

        response = {'error': None,
                    'message': _('Files moved successfully')}
        return self.create_response(request, response)

    def sword_collection(self, request, **kwargs):
        location = get_object_or_None(Location, uuid=kwargs['uuid'])
        if location and (location.purpose != Location.SWORD_DEPOSIT or location.space.access_protocol != Space.FEDORA):
            return http.HttpBadRequest(_('This is not a SWORD server space.'))
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
    related_packages = fields.ManyToManyField('self', 'related_packages', null=True)

    class Meta:
        queryset = Package.objects.all()
        authentication = MultiAuthentication(BasicAuthentication(), ApiKeyAuthentication(), SessionAuthentication())
        authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=PackageForm)
        #
        # Note that this resource is exposed as 'file' to the API for
        # compatibility because the resource itself was originally under
        # that name.
        resource_name = 'file'

        fields = ['current_path', 'package_type', 'size', 'status', 'uuid', 'related_packages', 'misc_attributes']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'put', 'patch']
        allowed_patch_fields = ['reingest']  # for customized update_in_place
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'location': ALL_WITH_RELATIONS,
            'package_type': ALL,
            'path': ALL,
            'uuid': ALL,
            'status': ALL,
            'related_packages': ALL_WITH_RELATIONS
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/delete_aip%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('delete_aip_request'), name="delete_aip_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/recover_aip%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('recover_aip_request'), name="recover_aip_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/extract_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('extract_file_request'), name="extract_file_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/download/(?P<chunk_number>\d+)%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('download_request'), name="download_lockss"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/download%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('download_request'), name="download_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/pointer_file%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('pointer_file_request'), name="pointer_file_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/check_fixity%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('check_fixity_request'), name="check_fixity_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/send_callback/post_store%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('aip_store_callback_request'), name="aip_store_callback_request"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/contents%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view("manage_contents"), name="manage_contents"),
            url(r"^(?P<resource_name>%s)/metadata%s$" % (self._meta.resource_name, trailing_slash()), self.wrap_view("file_data"), name="file_data"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/reindex%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('reindex_request'), name="reindex_request"),
            # Reingest
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/reingest%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('reingest_request'), name="reingest_request"),

            # FEDORA/SWORD2 endpoints
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit'), name="sword_deposit"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/media%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit_media'), name="sword_deposit_media"),
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/sword/state%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('sword_deposit_state'), name="sword_deposit_state"),
        ]

    def dehydrate_misc_attributes(self, bundle):
        """Customize serialization of misc_attributes."""
        # Serialize JSONField as dict, not as repr of a dict
        return bundle.obj.misc_attributes

    def obj_create(self, bundle, **kwargs):
        bundle = super(PackageResource, self).obj_create(bundle, **kwargs)
        related_package_uuid = bundle.data.get('related_package_uuid')
        # IDEA add custom endpoints, instead of storing all AIPS that come in?
        origin_location_uri = bundle.data.get('origin_location')
        origin_location = self.origin_location.build_related_resource(origin_location_uri, bundle.request).obj
        origin_path = bundle.data.get('origin_path')
        if bundle.obj.package_type in (Package.AIP, Package.AIC, Package.DIP) and bundle.obj.current_location.purpose in (Location.AIP_STORAGE, Location.DIP_STORAGE):
            # Store AIP/AIC
            bundle.obj.store_aip(origin_location, origin_path, related_package_uuid)
        elif bundle.obj.package_type in (Package.TRANSFER,) and bundle.obj.current_location.purpose in (Location.BACKLOG,):
            # Move transfer to backlog
            bundle.obj.backlog_transfer(origin_location, origin_path)
        return bundle

    def obj_update(self, bundle, skip_errors=False, **kwargs):
        """
        Modified version of the Django ORM implementation of obj_update.

        Identical to original function except obj_update_hook added between hydrating the data and saving the object.
        """
        if not bundle.obj or not self.get_bundle_detail_data(bundle):
            try:
                lookup_kwargs = self.lookup_kwargs_with_identifiers(bundle, kwargs)
            except:
                # if there is trouble hydrating the data, fall back to just
                # using kwargs by itself (usually it only contains a "pk" key
                # and this will work fine.
                lookup_kwargs = kwargs
            try:
                bundle.obj = self.obj_get(bundle=bundle, **lookup_kwargs)
            except ObjectDoesNotExist:
                raise tastypie.exceptions.NotFound(_("A model instance matching the provided arguments could not be found."))
        bundle = self.full_hydrate(bundle)
        bundle = self.obj_update_hook(bundle, **kwargs)
        return self.save(bundle, skip_errors=skip_errors)

    def obj_update_hook(self, bundle, **kwargs):
        """
        Hook to update Package and move files around before package is saved.

        bundle.obj has been updated, but not yet saved.
        """
        # PATCH should be only for updating metadata, not actually moving files.
        # Don't do any additional processing.
        if bundle.request.method == 'PATCH':
            # Update reingest - should only be notifications of done/failed
            if 'reingest' in bundle.data:
                bundle.obj.misc_attributes.update({'reingest_pipeline': None})
            return bundle
        origin_location_uri = bundle.data.get('origin_location')
        origin_path = bundle.data.get('origin_path')
        if origin_location_uri and origin_path:
            # Sending origin information implies that the package should be copied from there
            origin_location = self.origin_location.build_related_resource(origin_location_uri, bundle.request).obj
            if (bundle.obj.package_type in (Package.AIP, Package.AIC) and
                    bundle.obj.current_location.purpose in (Location.AIP_STORAGE) and
                    'reingest' in bundle.data):
                # AIP Reingest
                # Reset the current Location & path to original values
                # Package.finish_reingest will update them if successful
                original_package = self._meta.queryset.get(uuid=bundle.obj.uuid)
                bundle.obj.current_path = original_package.current_path
                bundle.obj.current_location = original_package.current_location
                reingest_location = self.origin_location.build_related_resource(bundle.data['current_location'], bundle.request).obj
                reingest_path = bundle.data['current_path']
                bundle.obj.finish_reingest(origin_location, origin_path,
                    reingest_location, reingest_path)
        return bundle

    def update_in_place(self, request, original_bundle, new_data):
        """
        Update the object in original_bundle in-place using new_data.

        Overridden to restrict what fields can be updated to only
        `allowed_patch_fields`.
        """
        # From http://stackoverflow.com/questions/13704344/tastypie-where-to-restrict-fields-that-may-be-updated-by-patch
        if set(new_data.keys()) - set(self._meta.allowed_patch_fields):
            raise tastypie.exceptions.BadRequest(
                _('PATCH only allowed on %(fields)s') %
                {'fields': ', '.join(self._meta.allowed_patch_fields)}
            )
        return super(PackageResource, self).update_in_place(request, original_bundle, new_data)

    @_custom_endpoint(expected_methods=['post'],
        required_fields=('event_reason', 'pipeline', 'user_id', 'user_email'))
    def delete_aip_request(self, request, bundle, **kwargs):
        """Create a delete request for an AIP. Does not perform the deletion."""
        request_info = bundle.data
        package = bundle.obj
        if package.package_type not in Package.PACKAGE_TYPE_CAN_DELETE:
            # Can only request deletion on AIPs
            response = {
                "message": _("Deletes not allowed on this package type.")
            }
            response_json = json.dumps(response)
            return http.HttpMethodNotAllowed(response_json, content_type='application/json')

        (status_code, response) = self._attempt_package_request_event(
            package, request_info, Event.DELETE, Package.DEL_REQ)

        if status_code == 202:
            # This isn't configured by default
            site_url = getattr(settings, "SITE_BASE_URL", None)
            signals.deletion_request.send(sender=self, url=site_url,
                uuid=package.uuid, location=package.full_path)
        else:
            response = {
                'message': _('A deletion request already exists for this AIP.')
            }

        self.log_throttled_access(request)
        response_json = json.dumps(response)
        return http.HttpResponse(status=status_code, content=response_json,
            content_type='application/json')

    @_custom_endpoint(expected_methods=['post'],
        required_fields=('event_reason', 'pipeline', 'user_id', 'user_email'))
    def recover_aip_request(self, request, bundle, **kwargs):
        request_info = bundle.data
        package = bundle.obj
        if package.package_type not in Package.PACKAGE_TYPE_CAN_RECOVER:
            # Can only request recovery of AIPs
            response = {
                "message": _("Recovery not allowed on this package type.")
            }
            response_json = json.dumps(response)
            return http.HttpMethodNotAllowed(response_json, content_type='application/json')

        (status_code, response) = self._attempt_package_request_event(
            package, request_info, Event.RECOVER, Package.RECOVER_REQ)

        self.log_throttled_access(request)
        response_json = json.dumps(response)
        return http.HttpResponse(status=status_code, content=response_json,
            content_type='application/json')

    @_custom_endpoint(expected_methods=['get', 'head'])
    def extract_file_request(self, request, bundle, **kwargs):
        """Return a single file from the Package, extracting if necessary."""
        # NOTE this responds to HEAD because AtoM uses HEAD to check for the existence of a file. The storage service has no way to check if a file exists except by downloading and extracting this AIP
        # TODO this needs to be fixed so that HEAD is not identical to GET

        relative_path_to_file = request.GET.get('relative_path_to_file')
        if not relative_path_to_file:
            return http.HttpBadRequest(_('All of these fields must be provided: relative_path_to_file'))
        relative_path_to_file = urllib.unquote(relative_path_to_file)
        temp_dir = extracted_file_path = ''

        # Get Package details
        package = bundle.obj

        # Handle package name duplication in path for compressed packages
        if not package.is_compressed:
            full_path = package.fetch_local_path()
            # The basename of the AIP may be included with the request, because
            # all AIPs contain a base directory. That directory may already be
            # inside the full path though, so remove the basename only if the
            # relative path begins with it.
            basename = os.path.join(os.path.basename(full_path), '')
            if relative_path_to_file.startswith(basename):
                relative_path_to_file = relative_path_to_file.replace(basename, '', 1)

        # Check if the package is in Arkivum and not actually there
        if package.current_location.space.access_protocol == Space.ARKIVUM:
            is_local = package.current_location.space.get_child_space().is_file_local(
                package,
                path=relative_path_to_file,
                email_nonlocal=request.method == 'GET',
            )
            if is_local is False:
                # Need to fetch from tape, return 202
                return http.HttpAccepted(json.dumps({"error": False, 'message': _("File is not locally available.  Contact your storage administrator to fetch it.")}))
            if is_local is None:
                # Arkivum error, return 502
                return http.HttpResponse(json.dumps({"error": True, "message": _("Error checking if file in Arkivum in locally available.")}), content_type='application/json', status=502)

        # If local file exists - return that
        if not package.is_compressed:
            extracted_file_path = os.path.join(full_path, relative_path_to_file)
            if not os.path.exists(extracted_file_path):
                return http.HttpResponse(status=404, content=_('Requested file, %(filename)s, not found in AIP') % {'filename': relative_path_to_file})
        elif package.package_type in Package.PACKAGE_TYPE_CAN_EXTRACT:
            # If file doesn't exist, try to extract it
            (extracted_file_path, temp_dir) = package.extract_file(relative_path_to_file)
        else:
            # If the package is compressed and we can't extract it,
            return http.HttpResponse(status=501, content=_('Unable to extract package of type: %(typename)s') % {'typename': package.package_type})

        response = utils.download_file_stream(extracted_file_path, temp_dir)

        return response

    @_custom_endpoint(expected_methods=['get', 'head'])
    def download_request(self, request, bundle, **kwargs):
        """Return the entire Package to be downloaded."""
        # NOTE this responds to HEAD because AtoM uses HEAD to check for the existence of a package. The storage service has no way to check if the package still exists except by downloading it
        # TODO this needs to be fixed so that HEAD is not identical to GET
        # Get AIP details
        package = bundle.obj
        # Check if the package is in Arkivum and not actually there
        if package.current_location.space.access_protocol == Space.ARKIVUM:
            is_local = package.current_location.space.get_child_space().is_file_local(
                package,
                email_nonlocal=request.method == 'GET',
            )
            if is_local is False:
                # Need to fetch from tape, return 202
                return http.HttpAccepted(json.dumps({"error": False, 'message': _("File is not locally available.  Contact your storage administrator to fetch it.")}))
            if is_local is None:
                # Arkivum error, return 502
                return http.HttpResponse(json.dumps({"error": True, "message": _("Error checking if file in Arkivum in locally available.")}), content_type='application/json', status=502)
        lockss_au_number = kwargs.get('chunk_number')
        try:
            temp_dir = None
            full_path = package.get_download_path(lockss_au_number)
        except StorageException:
            full_path, temp_dir = package.compress_package(utils.COMPRESSION_TAR)
        response = utils.download_file_stream(full_path)
        return response

    @_custom_endpoint(expected_methods=['get'])
    def pointer_file_request(self, request, bundle, **kwargs):
        """Return AIP pointer file."""
        # Get AIP details
        pointer_path = bundle.obj.full_pointer_file_path
        if not pointer_path:
            response = http.HttpNotFound(_("Resource with UUID %(uuid)s does not have a pointer file") % {'uuid': bundle.obj.uuid})
        else:
            response = utils.download_file_stream(pointer_path)
        return response

    @_custom_endpoint(expected_methods=['get'])
    def check_fixity_request(self, request, bundle, **kwargs):
        """
        Check a package's bagit/fixity.

        :param force_local: GET parameter. If True, will ignore any space-specific bagit checks and run it locally.
        """
        force_local = False
        if request.GET.get('force_local') in ('True', 'true', '1'):
            force_local = True
        success, failures, message, timestamp = bundle.obj.check_fixity(force_local=force_local)

        response = {
            "success": success,
            "message": message,
            "failures": {
                "files": {
                    "missing": [],
                    "changed": [],
                    "untracked": [],
                }
            },
            "timestamp": timestamp,
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
        if success is False:
            signals.failed_fixity_check.send(sender=self,
                uuid=bundle.obj.uuid, location=bundle.obj.full_path,
                report=report)
        elif success is None:
            signals.fixity_check_not_run.send(sender=self,
                uuid=bundle.obj.uuid, location=bundle.obj.full_path,
                report=report)
        elif success is True:
            signals.successful_fixity_check.send(sender=self,
                uuid=bundle.obj.uuid, location=bundle.obj.full_path,
                report=report)

        return http.HttpResponse(
            report,
            content_type="application/json"
        )

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
        for f, checksums in bag.entries.items():
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
                LOGGER.warning("Multiple File entries found for sha512 %s", cksum)

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
                "message": _("Failed to POST %(count)d responses to callback URI") % {'count': fail},
                "failure_count": fail,
                "callback_uris": [c.uri for c in callbacks]
            }
            return http.HttpApplicationError(
                json.dumps(response),
                content_type="application/json"
            )
        else:
            return http.HttpNoContent()

    @_custom_endpoint(expected_methods=['post'])
    def reindex_request(self, request, bundle, **kwargs):
        """Index file data from the Package transfer METS file."""
        package = bundle.obj
        if package.package_type != Package.TRANSFER:
            return http.HttpBadRequest(json.dumps({"error": True, "message": _("This package is not a transfer.")}), content_type='application/json')
        if package.current_location.purpose != Location.BACKLOG:
            return http.HttpBadRequest(json.dumps({"error": True, "message": _("This package is not in transfer backlog.")}), content_type='application/json')
        try:
            package.index_file_data_from_transfer_mets()  # Create File entries for every file in the transfer
        except Exception as e:
            LOGGER.warning("An error occurred while reindexing the Transfer: %s", str(e), exc_info=True)
            return http.HttpApplicationError(json.dumps({"error": True, "message": _("An error occurred while reindexing the Transfer.")}), content_type='application/json')
        count = File.objects.filter(package=package).count()
        response = {"error": False, "message": _("Files indexed: %(count)d") % {'count': count}}
        return http.HttpResponse(content=json.dumps(response), content_type='application/json')

    @_custom_endpoint(expected_methods=['post'],
        required_fields=('pipeline', 'reingest_type'))
    def reingest_request(self, request, bundle, **kwargs):
        try:
            pipeline = Pipeline.objects.get(uuid=bundle.data['pipeline'])
        except (Pipeline.DoesNotExist, Pipeline.MultipleObjectsReturned):
            response = {
                'error': True,
                'message': _('Pipeline UUID %(uuid)s failed to return a pipeline') % {'uuid': bundle.data['pipeline']},
            }
            return self.create_response(request, response, response_class=http.HttpBadRequest)
        reingest_type = bundle.data['reingest_type']
        processing_config = bundle.data.get('processing_config', 'default')

        response = bundle.obj.start_reingest(pipeline, reingest_type, processing_config)
        status_code = response.get('status_code', 500)

        return self.create_response(request, response, status=status_code)

    def sword_deposit(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest(_('This is not a SWORD deposit location.'))
        self.log_throttled_access(request)
        return sword_views.deposit_edit(request, package or kwargs['uuid'])

    def sword_deposit_media(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest(_('This is not a SWORD deposit location.'))
        self.log_throttled_access(request)
        return sword_views.deposit_media(request, package or kwargs['uuid'])

    def sword_deposit_state(self, request, **kwargs):
        package = get_object_or_None(Package, uuid=kwargs['uuid'])
        if package and package.package_type != Package.DEPOSIT:
            return http.HttpBadRequest(_('This is not a SWORD deposit location.'))
        self.log_throttled_access(request)
        return sword_views.deposit_state(request, package or kwargs['uuid'])

    def _attempt_package_request_event(self, package, request_info, event_type, event_status):
        pipeline = Pipeline.objects.get(uuid=request_info['pipeline'])
        request_description = event_type.replace('_', ' ').lower()

        # See if an event already exists
        existing_requests = Event.objects.filter(package=package,
            event_type=event_type, status=Event.SUBMITTED).count()
        if existing_requests < 1:
            request_event = Event(package=package, event_type=event_type,
                status=Event.SUBMITTED, event_reason=request_info['event_reason'],
                pipeline=pipeline, user_id=request_info['user_id'],
                user_email=request_info['user_email'], store_data=package.status)
            request_event.save()

            # Update package status
            package.status = event_status
            package.save()

            response = {
                'message': _("%(event_type)s request created successfully.") % {'event_type': request_description.title()},
                'id': request_event.id,
            }

            status_code = 202
        else:
            response = {
                'error_message': _("A %(event_type)s request already exists for this AIP.") % {'event_type': request_description},
            }
            status_code = 200

        return (status_code, response)

    @_custom_endpoint(expected_methods=['get', 'put', 'delete'])
    def manage_contents(self, request, bundle, **kwargs):
        if request.method == 'PUT':
            return self._add_files_to_package(request, bundle, **kwargs)
        elif request.method == 'DELETE':
            return self._remove_files_from_package(request, bundle, **kwargs)
        elif request.method == 'GET':
            return self._package_contents(request, bundle, **kwargs)

    def _remove_files_from_package(self, request, bundle, **kwargs):
        """
        Removes all file records associated with this package.
        """

        bundle.obj.file_set.all().delete()
        return http.HttpNoContent()

    def _add_files_to_package(self, request, bundle, **kwargs):
        """
        Adds a set of files to a package.

        The PUT body must be a list of zero or more JavaScript objects in the following format:
        {
            "relative_path": "string",
            "fileuuid": "string",
            "accessionid", "string",
            "sipuuid": "string",
            "origin": "string"
        }
        """

        try:
            files_list = json.load(request)
        except ValueError:
            response = {
                "success": False,
                "error": _("No JSON object could be decoded from POST body.")
            }
            return http.HttpBadRequest(json.dumps(response),
                content_type="application/json")

        if not isinstance(files_list, list):
            response = {
                "success": False,
                "error": _("JSON request must contain a list of objects.")
            }
            return http.HttpBadRequest(json.dumps(response),
                content_type="application/json")

        property_map = {
            "relative_path": "name",
            "fileuuid": "source_id",
            "accessionid": "accessionid",
            "sipuuid": "source_package",
            "origin": "origin",
        }

        if len(files_list) == 0:
            return http.HttpResponse()

        created_files = []
        for f in files_list:
            kwargs = {
                "package": bundle.obj
            }
            for source, dest in property_map.items():
                try:
                    kwargs[dest] = f[source]
                except KeyError:
                    response = {
                        "success": False,
                        "error": _('File object was missing key: %(key)s') % {'key': source},
                    }
                    return http.HttpBadRequest(json.dumps(response),
                        content_type="application_json")

            created_files.append(File(**kwargs))

        for f in created_files:
            f.save()

        response = {
            "success": True,
            "message": _("%(count)d files created in package %(uuid)s") % {'count': len(created_files), 'uuid': bundle.obj.uuid},
        }
        return http.HttpCreated(json.dumps(response),
            content_type="application_json")

    def _package_contents(self, request, bundle, **kwargs):
        """
        Returns metadata about every file within a specified Storage Service
        package, specified via Storage Service UUID.

        The file properties provided are the properties of the ~:class:`~locations.models.event.File` class; see the class definition for more information.

        :returns: a JSON object in the following format:
        {
            "success": True,
            "package": "UUID (as string)",
            "files": [
                # array containing zero or more objects containing
                # all of the file's properties, in the format:
                {
                    "source_id": "",
                    # ...
                }
            ]
        }
        """
        response = {
            "success": True,
            "package": bundle.obj.uuid,
            "files": []
        }

        for f in bundle.obj.file_set.all():
            response["files"].append({attr: getattr(f, attr) for attr in ('source_id', 'name', 'source_package', 'checksum', 'accessionid', 'origin')})

        return http.HttpResponse(status=200, content=json.dumps(response),
            content_type='application/json')

    def file_data(self, request, **kwargs):
        """
        Returns file metadata as a JSON array of objects.

        This maps properties of the File class to the names of the
        Elasticsearch indices' Transferfile index, allowing this to directly
        substitute for Elasticsearch when looking up metadata on specific files.

        Acceptable parameters are:
            * relative_path (searches the `name` field)
            * fileuuid (searches the `source_id` field)
            * accessionid (searches the `accessionid` field)
            * sipuuid (searches the `source_package` field)

        :returns: an array of one or more objects. See the transferfile
        index for information on the return format.
        If no results are found for the specified query, returns 404.
        If no acceptable query parameters are found, returns 400.
        """
        # Tastypie API checks
        self.method_check(request, allowed=['get', 'post'])
        self.is_authenticated(request)
        self.throttle_check(request)
        self.log_throttled_access(request)

        property_map = {
            "relative_path": "name",
            "fileuuid": "source_id",
            "accessionid": "accessionid",
            "sipuuid": "source_package"
        }
        query = {}
        for source, dest in property_map.items():
            try:
                query[dest] = request.GET[source]
            except KeyError:
                pass

        if not query:
            response = {
                "success": False,
                "error": _("No supported query properties found!")
            }
            return http.HttpBadRequest(content=json.dumps(response),
                content_type="application/json")

        files = File.objects.filter(**query)
        if not files.exists():
            return http.HttpNotFound()

        response = []
        for f in files:
            response.append({
                "accessionid": f.accessionid,
                "file_extension": os.path.splitext(f.name)[1],
                "filename": os.path.basename(f.name),
                "relative_path": f.name,
                "fileuuid": f.source_id,
                "origin": f.origin,
                "sipuuid": f.source_package
            })

        return http.HttpResponse(content=json.dumps(response), content_type="application/json")
