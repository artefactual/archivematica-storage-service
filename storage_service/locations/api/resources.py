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

        fields = ['access_protocol', 'location_set', 'path', 'size', 'used', 'uuid', 'verified']
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

    # override hydrate/dehydrate to add full Space info?
    # Is there a better place?
    # alter_detail_data_to_serialize
    # alter_deserialized_detail_data

    # Mapping between access protocol and protocol specific fields
    protocol = {}
    # BUG: fields: [] works for obj_create, but includes everything in dehydrate
    protocol['FS'] = {'model': LocalFilesystem, 'fields': ['nothing'] }
    protocol['SAMBA'] = {'model': Samba, 'fields': ['remote_name', 'username'] }

    def dehydrate(self, bundle):
        """ Add protocol specific fields to an entry. """
        bundle = super(SpaceResource, self).dehydrate(bundle)
        print 'dehydrate bundle', type(bundle), bundle
        print 'access_protocol', bundle.obj.access_protocol
        access_protocol = bundle.obj.access_protocol
        model = self.protocol[access_protocol]['model']
        print 'protocol', self.protocol[access_protocol]

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
        # TODO should this be in the model?
        bundle = super(SpaceResource, self).obj_create(bundle, **kwargs)
        access_protocol = bundle.obj.access_protocol
        model = self.protocol[access_protocol]['model']
        fields = self.protocol[access_protocol]['fields']

        # Make dict of fields in model and values from bundle.data
        fields_dict = { key: bundle.data[key] for key in fields }
        obj = model.objects.create(space=bundle.obj, **fields_dict)
        obj.save()
        return bundle


class LocationResource(ModelResource):
    space = fields.ForeignKey(SpaceResource, 'storage_space')
    class Meta:
        queryset = Location.objects.filter(disabled=False)
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        validation = CleanedDataFormValidation(form_class=LocationForm)

        fields = ['path', 'purpose', 'quota', 'storage_space', 'used', 'uuid']
        list_allowed_methods = ['get', 'post']
        detail_allowed_methods = ['get', 'patch']
        detail_uri_name = 'uuid'
        always_return_data = True
        filtering = {
            'path': ALL,
            'purpose': ALL,
            'quota': ALL,
            'storage_space': ALL,
            'used': ALL,
            'uuid': ALL,
        }

    def dehydrate(self, bundle):
        bundle = super(LocationResource, self).dehydrate(bundle)
        # Include full path (space path + location path)
        bundle.data['full_path'] = os.path.join(bundle.obj.storage_space.path, bundle.obj.path)
        return bundle
