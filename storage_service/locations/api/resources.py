from tastypie.authorization import Authorization
from tastypie.authentication import BasicAuthentication, ApiKeyAuthentication, MultiAuthentication, Authentication
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS

from ..models import Location

class LocationResource(ModelResource):
    class Meta:
        queryset = Location.objects.all()
        resource_name = 'location'
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()

        filtering = {
            "id": ALL,
            "purpose": ALL,
            "access_protocol": ALL,
            "path": ALL,
            "quota": ALL,
            "used": ALL,
        }
