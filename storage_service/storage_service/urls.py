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
    import django.core.exceptions
    import errno
    import os.path
    from locations import models as locations_models
    from common import utils
    import logging
    LOGGER = logging.getLogger(__name__)
    LOGGER.info("Running startup")
    try:
        space, space_created = locations_models.Space.objects.get_or_create(
            access_protocol=locations_models.Space.LOCAL_FILESYSTEM,
            path=os.sep, defaults={
                "staging_path": os.path.join(os.sep, 'var', 'archivematica', 'storage_service')
            })
        if space_created:
            locations_models.LocalFilesystem.objects.create(space=space)
            LOGGER.info('Created default Space %s', space)
    except django.core.exceptions.MultipleObjectsReturned:
        LOGGER.info('Multiple default Spaces exist, done default setup.')
        return

    default_locations = [
        {
            'purpose': locations_models.Location.TRANSFER_SOURCE,
            'relative_path': 'home',
            'description': '',
            'default_setting': 'default_transfer_source',
        },
        {
            'purpose': locations_models.Location.AIP_STORAGE,
            'relative_path': os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'AIPsStore'),
            'description': 'Store AIP in standard Archivematica Directory',
            'default_setting': 'default_aip_storage',
        },
        {
            'purpose': locations_models.Location.DIP_STORAGE,
            'relative_path': os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'DIPsStore'),
            'description': 'Store DIP in standard Archivematica Directory',
            'default_setting': 'default_dip_storage',
        },
        {
            'purpose': locations_models.Location.BACKLOG,
            'relative_path': os.path.join('var', 'archivematica', 'sharedDirectory', 'www', 'AIPsStore', 'transferBacklog'),
            'description': 'Default transfer backlog',
            'default_setting': 'default_backlog',
        },
        {
            'purpose': locations_models.Location.STORAGE_SERVICE_INTERNAL,
            'relative_path': os.path.join('var', 'archivematica', 'storage_service'),
            'description': 'For storage service internal usage.',
            'default_setting': None,
            'create_dirs': True,
        },
        {
            'purpose': locations_models.Location.AIP_RECOVERY,
            'relative_path': os.path.join('var', 'archivematica', 'storage_service', 'recover'),
            'description': 'Default AIP recovery',
            'default_setting': 'default_recovery',
            'create_dirs': True,
        },
    ]

    for loc_info in default_locations:
        try:
            new_loc, created = locations_models.Location.objects.get_or_create(
                purpose=loc_info['purpose'],
                space=space,
                relative_path=loc_info['relative_path'],
                description=loc_info['description'])
            if created:
                LOGGER.info('Created default %s Location %s', loc_info['purpose'], new_loc)
        except locations_models.Location.MultipleObjectsReturned:
            continue

        if created and loc_info.get('create_dirs'):
            LOGGER.info('Creating %s Location %s', loc_info['purpose'], new_loc)
            try:
                os.mkdir(new_loc.full_path)
                # Hack for extra recovery dir
                if loc_info['purpose'] == locations_models.Location.AIP_RECOVERY:
                    os.mkdir(os.path.join(new_loc.full_path, 'backup'))
            except OSError as e:
                if e.errno != errno.EEXIST:
                    LOGGER.error("%s location %s not accessible.", loc_info['purpose'], new_loc.full_path)

        if loc_info['default_setting'] and utils.get_setting(loc_info['default_setting']) is None:
            utils.set_setting(loc_info['default_setting'], [new_loc.uuid])
            LOGGER.info('Set %s as %s', new_loc, loc_info['default_setting'])


startup()
