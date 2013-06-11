from tastypie.authentication import BasicAuthentication, ApiKeyAuthentication, MultiAuthentication, Authentication
from tastypie.authorization import DjangoAuthorization, Authorization
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS
from tastypie.validation import CleanedDataFormValidation

from ..models import Location, LocationForm

class LocationResource(ModelResource):
    class Meta:
        queryset = Location.objects.all()
        authentication = Authentication()
        # authentication = MultiAuthentication(BasicAuthentication, ApiKeyAuthentication())
        authorization = Authorization()
        # authorization = DjangoAuthorization()
        always_return_data = True
        validation = CleanedDataFormValidation(form_class=LocationForm)

        filtering = {
            "id": ALL,
            "purpose": ALL,
            "access_protocol": ALL,
            "path": ALL,
            "quota": ALL,
            "used": ALL,
        }
