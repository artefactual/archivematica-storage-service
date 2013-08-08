from django.conf.urls import patterns, include, url
from django.views.generic import TemplateView

import administration.urls
import locations.urls
import locations.api.urls

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', TemplateView.as_view(template_name='index.html')),

    # Examples:
    # url(r'^$', 'storage_service.views.home', name='home'),
    # url(r'^storage_service/', include('storage_service.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),

    url(r'^', include(locations.urls)),
    url(r'^administration/', include(administration.urls)),
    url(r'^login/$', 'django.contrib.auth.views.login',
        {'template_name': 'login.html'}),
    url(r'^logout/$', 'django.contrib.auth.views.logout_then_login',
        name='logout'),

    url(r'^api/', include(locations.api.urls)),
)
