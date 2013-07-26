from django.conf.urls import *
from django.forms.models import model_to_dict

import json
from tastypie.authentication import (BasicAuthentication, ApiKeyAuthentication,
    MultiAuthentication, Authentication)
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie import fields
from tastypie import http
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation
from tastypie.utils import trailing_slash

from ..models import (Event, File, Location, Space, Pipeline)
from ..forms import LocationForm, SpaceForm

import common.constants

# FIXME ModelResources with ForeignKeys to another model don't work with
# validation = CleanedDataFormValidation  On creation, it errors with:
# "Select a valid choice. That choice is not one of the available choices."
# This is because the ModelResource accepts a URI, but does not convert it to a
# primary key (in our case, UUID) before passing it to Django.
# See https://github.com/toastdriven/django-tastypie/issues/152 for details


class PipelineResource(ModelResource):
    class Meta:
        queryset = Pipeline.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=FileForm)

        fields = ['uuid', 'description']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'description': ALL,
            'uuid': ALL,
        }


class SpaceResource(ModelResource):
    class Meta:
        queryset = Space.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        validation = CleanedDataFormValidation(form_class=SpaceForm)

        fields = ['access_protocol', 'last_verified', 'location_set', 'path',
            'size', 'used', 'uuid', 'verified']
        list_allowed_methods = ['get', 'post']
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

    # Is there a better place to add protocol-specific space info?
    # alter_detail_data_to_serialize
    # alter_deserialized_detail_data

    def dehydrate(self, bundle):
        """ Add protocol specific fields to an entry. """
        bundle = super(SpaceResource, self).dehydrate(bundle)
        access_protocol = bundle.obj.access_protocol
        model = common.constants.PROTOCOL[access_protocol]['model']

        try:
            space = model.objects.get(space=bundle.obj.uuid)
        except model.DoesNotExist:
            print "Item doesn't exist :("
            # TODO this should assert later once creation/deletion stuff works
        else:
            keep_fields = common.constants.PROTOCOL[access_protocol]['fields']
            added_fields = model_to_dict(space, keep_fields)
            bundle.data.update(added_fields)

        return bundle

    def obj_create(self, bundle, **kwargs):
        """ Creates protocol specific class when creating a Space. """
        # TODO How to move this to the model?
        # Make dict of fields in model and values from bundle.data
        access_protocol = bundle.data['access_protocol']
        keep_fields = common.constants.PROTOCOL[access_protocol]['fields']
        fields_dict = { key: bundle.data[key] for key in keep_fields }

        bundle = super(SpaceResource, self).obj_create(bundle, **kwargs)

        model = common.constants.PROTOCOL[access_protocol]['model']
        obj = model.objects.create(space=bundle.obj, **fields_dict)
        obj.save()
        return bundle

    # TODO only accept 'post's from dashboard for local filesystem


class LocationResource(ModelResource):
    space = fields.ForeignKey(SpaceResource, 'space')
    path = fields.CharField(attribute='full_path', readonly=True)
    description = fields.CharField(attribute='get_description', readonly=True)
    pipeline = fields.ForeignKey(PipelineResource, 'pipeline', full=True)

    class Meta:
        queryset = Location.objects.filter(disabled=False)
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=LocationForm)

        fields = ['disabled', 'relative_path', 'purpose', 'quota', 'used', 'uuid']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'patch']
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


class FileResource(ModelResource):
    """ Resource for managing Files.

    List (api/v1/file/) supports:
    GET: List of files
    POST: Create new File

    Detail (api/v1/file/<uuid>/) supports:
    GET: Get details on a specific file

    api/v1/file/<uuid>/delete_aip/ supports:
    POST: Create a delete request for that AIP.
    """
    origin_location = fields.ForeignKey(LocationResource, 'origin_location')
    current_location = fields.ForeignKey(LocationResource, 'current_location')

    origin_full_path = fields.CharField(attribute='full_origin_path',
        readonly=True)
    current_full_path = fields.CharField(attribute='full_path', readonly=True)

    class Meta:
        queryset = File.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(
        #     BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=FileForm)

        fields = ['origin_path', 'current_path', 'package_type', 'size', 'status', 'uuid']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'location': ALL_WITH_RELATIONS,
            'path': ALL,
            'uuid': ALL,
        }

    def prepend_urls(self):
        return [
            url(r"^(?P<resource_name>%s)/(?P<%s>\w[\w/-]*)/delete_aip%s$" % (self._meta.resource_name, self._meta.detail_uri_name, trailing_slash()), self.wrap_view('delete_aip_request'), name="delete_aip_request"),
        ]

    def obj_create(self, bundle, **kwargs):
        bundle = super(FileResource, self).obj_create(bundle, **kwargs)
        # IDEA add custom endpoints, instead of storing all AIPS that come in?
        if bundle.obj.package_type == File.AIP:
            bundle.obj.current_location.space.store_aip(bundle.obj)
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
            return http.HttpBadRequest

        # Create the Event for file deletion request
        file = File.objects.get(uuid=kwargs['uuid'])
        if file.package_type != File.AIP:
            # Can only request deletion on AIPs
            return http.HttpMethodNotAllowed()

        pipeline = Pipeline.objects.get(uuid=request_info['pipeline'])
        delete_request = Event(file=file, event_type=Event.DELETE,
            status=Event.SUBMITTED, event_reason=request_info['event_reason'],
            pipeline=pipeline, user_id=request_info['user_id'],
            user_email=request_info['user_email'])
        delete_request.save()

        self.log_throttled_access(request)
        return http.HttpAccepted()
