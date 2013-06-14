from django.conf.urls import patterns, include, url
from tastypie.api import Api
from .resources import LocationResource, SpaceResource

v1_api = Api(api_name='v1')
v1_api.register(SpaceResource())
v1_api.register(LocationResource())


urlpatterns = patterns('',
    (r'', include(v1_api.urls)),
)
