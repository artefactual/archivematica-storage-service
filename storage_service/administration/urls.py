from django.urls import path

from administration import views

app_name = "administration"
urlpatterns = [
    # Sorted by alphabetized categories
    path("", views.index, name="index"),
    path("configuration/", views.configuration, name="configuration"),
    path("version/", views.version_view, name="version"),
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:id>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:id>/", views.user_detail, name="user_detail"),
    path("language/", views.change_language, name="change_language"),
    path("keys/", views.key_list, name="key_list"),
    path("keys/<str:key_fingerprint>/detail", views.key_detail, name="key_detail"),
    path("keys/create/", views.key_create, name="key_create"),
    path("keys/import/", views.key_import, name="key_import"),
    path(
        "keys/<str:key_fingerprint>/delete/",
        views.key_delete,
        name="key_delete",
    ),
]
