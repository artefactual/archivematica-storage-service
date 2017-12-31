from django.conf.urls import include, url
from tastypie.api import Api
from locations.api import v1, v2

from locations.api.sword import views

v1_api = Api(api_name='v1')
v1_api.register(v1.SpaceResource())
v1_api.register(v1.LocationResource())
v1_api.register(v1.PackageResource())
v1_api.register(v1.PipelineResource())

v2_api = Api(api_name='v2')
v2_api.register(v2.SpaceResource())
v2_api.register(v2.LocationResource())
v2_api.register(v2.PackageResource())
v2_api.register(v2.PipelineResource())

urlpatterns = [
    url(r'', include(v1_api.urls)),
    url(r'v1/sword/$', views.service_document, name='sword_service_document'),
    url(r'v1/doc/',
        include('tastypie_swagger.urls', namespace='v1_api_swagger'),
        kwargs={
            'tastypie_api_module': v1_api,
            'namespace': 'v1_api_swagger',
            'version': '2.0'}),
    url(r'', include(v2_api.urls)),
    url(r'v2/sword/$', views.service_document, name='sword_service_document'),
    url(r'v2/doc/',
        include('tastypie_swagger.urls', namespace='v2_api_swagger'),
        kwargs={
            'tastypie_api_module': v2_api,
            'namespace': 'v2_api_swagger',
            'version': '1.0'}),
]
