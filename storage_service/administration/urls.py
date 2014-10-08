from django.conf.urls import url
from administration import views

urlpatterns = [
    # Sorted by alphabetized categories

    url(r'^$', views.settings_edit,
        name='settings_edit'),

    url(r'^users/$', views.user_list,
        name='user_list'),
    url(r'^users/create/$', views.user_create,
        name='user_create'),
    url(r'^users/(?P<id>[-\w]+)/edit/$', views.user_edit,
        name='user_edit'),
]
