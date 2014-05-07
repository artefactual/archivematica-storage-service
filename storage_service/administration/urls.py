from django.conf.urls import patterns, url

urlpatterns = patterns('administration.views',
    # Sorted by alphabetized categories

    url(r'^$', 'settings_edit',
        name='settings_edit'),

    url(r'^users/$', 'user_list',
        name='user_list'),
    url(r'^users/create/$', 'user_create',
        name='user_create'),
    url(r'^users/(?P<id>[-\w]+)/edit/$', 'user_edit',
        name='user_edit'),
)
