from django.conf.urls import url

from administration import views

app_name = "administration"
urlpatterns = [
    # Sorted by alphabetized categories
    url(r"^$", views.settings_edit, name="settings_edit"),
    url(r"^version/$", views.version_view, name="version"),
    url(r"^users/$", views.user_list, name="user_list"),
    url(r"^users/create/$", views.user_create, name="user_create"),
    url(r"^users/(?P<id>[-\w]+)/edit/$", views.user_edit, name="user_edit"),
    url(r"^users/(?P<id>[-\w]+)/$", views.user_detail, name="user_detail"),
    url(r"language/$", views.change_language, name="change_language"),
    url(r"^keys/$", views.key_list, name="key_list"),
    url(
        r"^keys/(?P<key_fingerprint>[\w]+)/detail$", views.key_detail, name="key_detail"
    ),
    url(r"^keys/create/$", views.key_create, name="key_create"),
    url(r"^keys/import/$", views.key_import, name="key_import"),
    url(
        r"^keys/(?P<key_fingerprint>[\w]+)/delete/$",
        views.key_delete,
        name="key_delete",
    ),
]
