from django.urls import include
from django.urls import path
from locations.api import v1
from locations.api import v2
from locations.api.sword import views
from tastypie.api import Api

v1_api = Api(api_name="v1")
v1_api.register(v1.SpaceResource())
v1_api.register(v1.LocationResource())
v1_api.register(v1.PackageResource())
v1_api.register(v1.PipelineResource())
v1_api.register(v1.AsyncResource())

v2_api = Api(api_name="v2")
v2_api.register(v2.SpaceResource())
v2_api.register(v2.LocationResource())
v2_api.register(v2.PackageResource())
v2_api.register(v2.PipelineResource())
v2_api.register(v2.AsyncResource())

urlpatterns = [
    path("", include(v1_api.urls)),
    path("v1/sword/", views.service_document, name="sword_service_document"),
    path("", include(v2_api.urls)),
    path("v2/sword/", views.service_document, name="sword_service_document"),
]
