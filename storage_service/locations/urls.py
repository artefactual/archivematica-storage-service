from django.urls import path

from locations import views

app_name = "locations"
urlpatterns = [
    # Sorted by alphabetized categories
    # Locations
    path("locations/", views.location_list, name="location_list"),
    path(
        "locations/<uuid:location_uuid>/",
        views.location_detail,
        name="location_detail",
    ),
    path(
        "locations/<uuid:location_uuid>/delete/",
        views.location_delete,
        name="location_delete",
    ),
    path(
        "locations/<uuid:location_uuid>/switch_enabled/",
        views.location_switch_enabled,
        name="location_switch_enabled",
    ),
    # Packages
    path("packages/", views.package_list, name="package_list"),
    path("packages_ajax/", views.package_list_ajax, name="package_list_ajax"),
    path(
        "packages/package_delete_request/",
        views.package_delete_request,
        name="package_delete_request",
    ),
    path(
        "packages/<uuid:uuid>/delete/",
        views.package_delete,
        name="package_delete",
    ),
    path(
        "packages/<uuid:uuid>/update_status/",
        views.package_update_status,
        name="package_update_status",
    ),
    path(
        "packages/aip_recover_request",
        views.aip_recover_request,
        name="aip_recover_request",
    ),
    path(
        "packages/<uuid:package_uuid>/reingest/",
        views.aip_reingest,
        name="aip_reingest",
    ),
    # Fixity check results
    path(
        "fixity/<uuid:package_uuid>/",
        views.package_fixity,
        name="package_fixity",
    ),
    path("fixity_ajax/", views.fixity_logs_ajax, name="fixity_logs_ajax"),
    # Pipelines
    path("pipelines/", views.pipeline_list, name="pipeline_list"),
    path("pipelines/create/", views.pipeline_edit, name="pipeline_create"),
    path(
        "pipeline/<uuid:uuid>/edit/",
        views.pipeline_edit,
        name="pipeline_edit",
    ),
    path(
        "pipeline/<uuid:uuid>/detail/",
        views.pipeline_detail,
        name="pipeline_detail",
    ),
    path(
        "pipeline/<uuid:uuid>/delete/",
        views.pipeline_delete,
        name="pipeline_delete",
    ),
    path(
        "pipeline/<uuid:uuid>/switch_enabled/",
        views.pipeline_switch_enabled,
        name="pipeline_switch_enabled",
    ),
    # Spaces
    path("spaces/", views.space_list, name="space_list"),
    path("spaces/<uuid:uuid>/", views.space_detail, name="space_detail"),
    path("spaces/<uuid:uuid>/edit/", views.space_edit, name="space_edit"),
    path(
        "spaces/<uuid:uuid>/delete/",
        views.space_delete,
        name="space_delete",
    ),
    path(
        "spaces/<uuid:space_uuid>/location_create/",
        views.location_edit,
        name="location_create",
    ),
    path(
        "spaces/<uuid:space_uuid>/location/<uuid:location_uuid>/edit/",
        views.location_edit,
        name="location_edit",
    ),
    path("spaces/create/", views.space_create, name="space_create"),
    # Spaces AJAX
    path(
        "spaces/get_form_type/",
        views.ajax_space_create_protocol_form,
        name="ajax_space_create_protocol_form",
    ),
    # Callbacks
    path("callbacks/", views.callback_list, name="callback_list"),
    path(
        "callbacks/<uuid:uuid>/",
        views.callback_detail,
        name="callback_detail",
    ),
    path("callbacks/create/", views.callback_edit, name="callback_create"),
    path(
        "callbacks/<uuid:uuid>/edit/",
        views.callback_edit,
        name="callback_edit",
    ),
    path(
        "callbacks/<uuid:uuid>/delete/",
        views.callback_delete,
        name="callback_delete",
    ),
    path(
        "callbacks/<uuid:uuid>/switch_enabled/",
        views.callback_switch_enabled,
        name="callback_switch_enabled",
    ),
]
