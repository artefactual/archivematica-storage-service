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


def startup():
    import errno
    import os.path
    from locations import models as locations_models
    from common import utils
    import logging
    LOGGER = logging.getLogger(__name__)
    LOGGER.info("Running startup")
    space, space_created = locations_models.Space.objects.get_or_create(
        access_protocol=locations_models.Space.LOCAL_FILESYSTEM,
        path=os.sep, defaults={
            "staging_path": os.path.join(os.sep, 'var', 'archivematica', 'storage_service')
        })
    if space_created:
        local_fs = locations_models.LocalFilesystem(space=space)
        local_fs.save()
    transfer_source, _ = locations_models.Location.objects.get_or_create(
        purpose=locations_models.Location.TRANSFER_SOURCE,
        space=space,
        relative_path='home')
    aip_storage, _ = locations_models.Location.objects.get_or_create(
        purpose=locations_models.Location.AIP_STORAGE,
        space=space,
        relative_path=os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'AIPsStore'),
        description='Store AIP in standard Archivematica Directory')
    dip_storage, _ = locations_models.Location.objects.get_or_create(
        purpose=locations_models.Location.DIP_STORAGE,
        space=space,
        relative_path=os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'DIPsStore'),
        description='Store DIP in standard Archivematica Directory')
    backlog, _ = locations_models.Location.objects.get_or_create(
        purpose=locations_models.Location.BACKLOG,
        space=space,
        relative_path=os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'AIPsStore', 'transferBacklog'),
        description='Default transfer backlog')
    internal_use, created = locations_models.Location.objects.get_or_create(
        purpose=locations_models.Location.STORAGE_SERVICE_INTERNAL,
        defaults={
            'space': space,
            'relative_path': os.path.join('var', 'archivematica', 'storage_service'),
            'description': 'For storage service internal usage.'
        }
    )
    if created:
        try:
            os.mkdir(internal_use.full_path)
        except OSError as e:
            if e.errno != errno.EEXIST:
                LOGGER.error("Internal storage location {} not accessible.".format(internal_use.full_path))

    if not utils.get_setting('default_transfer_source'):
        utils.set_setting('default_transfer_source', [transfer_source.uuid])
    if not utils.get_setting('default_aip_storage'):
        utils.set_setting('default_aip_storage', [aip_storage.uuid])
    if not utils.get_setting('default_dip_storage'):
        utils.set_setting('default_dip_storage', [dip_storage.uuid])
    if not utils.get_setting('default_backlog'):
        utils.set_setting('default_backlog', [backlog.uuid])

startup()
