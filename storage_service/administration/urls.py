from django.conf.urls import patterns, url

urlpatterns = patterns('administration.views',
    # Sorted by alphabetized categories

    url(r'^$', 'settings_edit',
        name='settings_edit'),
)
