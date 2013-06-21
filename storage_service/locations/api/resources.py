import os
import uuid

from django.forms.models import model_to_dict

from tastypie import fields
from tastypie.authentication import BasicAuthentication, ApiKeyAuthentication, MultiAuthentication, Authentication
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation
from ..models import (File, LocalFilesystem, Location, LocationForm, Samba, Space, SpaceForm)

class SpaceResource(ModelResource):
    class Meta:
        queryset = Space.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        validation = CleanedDataFormValidation(form_class=SpaceForm)

        fields = ['access_protocol', 'last_verified', 'location_set', 'path', 'size', 'used', 'uuid', 'verified']
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

    # Mapping between access protocol and protocol specific fields
    protocol = {}
    # BUG: fields: [] works for obj_create, but includes everything in dehydrate
    protocol['FS'] = {'model': LocalFilesystem, 'fields': [] }
    protocol['SAMBA'] = {'model': Samba, 'fields': ['remote_name', 'username'] }

    def dehydrate(self, bundle):
        """ Add protocol specific fields to an entry. """
        bundle = super(SpaceResource, self).dehydrate(bundle)
        access_protocol = bundle.obj.access_protocol
        model = self.protocol[access_protocol]['model']

        try:
            space = model.objects.get(space=bundle.obj.uuid)
        except model.DoesNotExist:
            print "Item doesn't exist :("
            # TODO this should assert later once creation/deletion stuff works
        else:
            fields = self.protocol[access_protocol]['fields']
            added_fields = model_to_dict(space, fields)
            bundle.data.update(added_fields)
        return bundle

    def obj_create(self, bundle, **kwargs):
        """ Creates protocol specific class when creating a Space. """
        # TODO How to move this to the model?
        # Make dict of fields in model and values from bundle.data
        access_protocol = bundle.data['access_protocol']
        fields = self.protocol[access_protocol]['fields']
        fields_dict = { key: bundle.data[key] for key in fields }

        bundle = super(SpaceResource, self).obj_create(bundle, **kwargs)

        model = self.protocol[access_protocol]['model']
        obj = model.objects.create(space=bundle.obj, **fields_dict)
        obj.save()
        return bundle

    # TODO only accept 'post's from dashboard for local filesystem


class LocationResource(ModelResource):
    space = fields.ForeignKey(SpaceResource, 'storage_space')
    class Meta:
        queryset = Location.objects.filter(disabled=False)
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        validation = CleanedDataFormValidation(form_class=LocationForm)

        fields = ['relative_path', 'purpose', 'quota', 'used', 'uuid']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'patch']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'relative_path': ALL,
            'purpose': ALL,
            'quota': ALL,
            'space': ALL,
            'used': ALL,
            'uuid': ALL,
        }

    def dehydrate(self, bundle):
        bundle = super(LocationResource, self).dehydrate(bundle)
        # Include full path (space path + location relative_path)
        bundle.data['path'] = bundle.obj.full_path()
        bundle.data['description'] = bundle.obj.get_description()
        return bundle


class FileResource(ModelResource):
    location = fields.ForeignKey(LocationResource, 'location')
    class Meta:
        queryset = File.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        # validation = CleanedDataFormValidation(form_class=FileForm)

        fields = ['path', 'size', 'uuid']
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get', 'put', 'post']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'location': ALL,
            'path': ALL,
            'uuid': ALL,
        }
