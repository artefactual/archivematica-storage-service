from django.conf.urls import patterns, url

UUID = r"\w{8}-\w{4}-\w{4}-\w{4}-\w{12}"

urlpatterns = patterns('locations.views',

    url(r'^spaces/$', 'space_list',
        name='space_list'),
    url(r'^spaces/(?P<uuid>'+UUID+')/$', 'space_detail',
        name='space_detail'),
    url(r'^spaces/(?P<space_uuid>'+UUID+')/location_create/$', 'location_create',
        name='location_create'),
    url(r'^spaces/create/$', 'space_create',
        name='space_create'),

    url(r'^spaces/get_form_type/$', 'ajax_space_create_protocol_form',
        name='ajax_space_create_protocol_form'),

    url(r'^locations/$', 'location_list',
        name='location_list'),

    url(r'^files/$', 'file_list',
        name='file_list'),
    url(r'^files/aip_delete_request$', 'aip_delete_request',
        name='aip_delete_request'),
)
