from django.conf.urls import patterns, url

UUID = r"\w{8}-\w{4}-\w{4}-\w{4}-\w{12}"

urlpatterns = patterns('locations.views',
    # Sorted by alphabetized categories

    # Locations
    url(r'^locations/$', 'location_list',
        name='location_list'),
    url(r'^locations/(?P<location_uuid>'+UUID+')/$', 'location_detail',
        name='location_detail'),
    url(r'^locations/(?P<location_uuid>'+UUID+')/delete/$', 'location_delete',
        name='location_delete'),

    # Packages
    url(r'^packages/$', 'package_list',
        name='package_list'),
    url(r'^packages/aip_delete_request$', 'aip_delete_request',
        name='aip_delete_request'),

    # Pipelines
    url(r'^pipelines/$', 'pipeline_list',
        name='pipeline_list'),
    url(r'^pipelines/create/$', 'pipeline_edit',
        name='pipeline_create'),
    url(r'^pipeline/(?P<uuid>'+UUID+')/edit/$', 'pipeline_edit',
        name='pipeline_edit'),
    url(r'^pipeline/(?P<uuid>'+UUID+')/detail/$', 'pipeline_detail',
        name='pipeline_detail'),
    url(r'^pipeline/(?P<uuid>'+UUID+')/delete/$', 'pipeline_delete',
        name='pipeline_delete'),


    # Spaces
    url(r'^spaces/$', 'space_list',
        name='space_list'),
    url(r'^spaces/(?P<uuid>'+UUID+')/$', 'space_detail',
        name='space_detail'),
    url(r'^spaces/(?P<uuid>'+UUID+')/edit/$', 'space_edit',
        name='space_edit'),
    url(r'^spaces/(?P<uuid>'+UUID+')/delete/$', 'space_delete',
        name='space_delete'),
    url(r'^spaces/(?P<space_uuid>'+UUID+')/location_create/$', 'location_edit',
        name='location_create'),
    url(r'^spaces/(?P<space_uuid>'+UUID+')/location/(?P<location_uuid>'+UUID+')/edit/$', 'location_edit',
        name='location_edit'),
    url(r'^spaces/create/$', 'space_create',
        name='space_create'),
    # Spaces AJAX
    url(r'^spaces/get_form_type/$', 'ajax_space_create_protocol_form',
        name='ajax_space_create_protocol_form'),
)
