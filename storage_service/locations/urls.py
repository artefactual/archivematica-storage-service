from django.urls import path
from django.urls import re_path
from locations import views

UUID = r"\w{8}-\w{4}-\w{4}-\w{4}-\w{12}"

app_name = "locations"
urlpatterns = [
    # Sorted by alphabetized categories
    # Locations
    path("locations/", views.location_list, name="location_list"),
    re_path(
        r"^locations/(?P<location_uuid>" + UUID + ")/$",
        views.location_detail,
        name="location_detail",
    ),
    re_path(
        r"^locations/(?P<location_uuid>" + UUID + ")/delete/$",
        views.location_delete,
        name="location_delete",
    ),
    re_path(
        r"^locations/(?P<location_uuid>" + UUID + ")/switch_enabled/$",
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
    re_path(
        r"^packages/(?P<uuid>" + UUID + ")/delete/$",
        views.package_delete,
        name="package_delete",
    ),
    re_path(
        r"^packages/(?P<uuid>" + UUID + ")/update_status/$",
        views.package_update_status,
        name="package_update_status",
    ),
    path(
        "packages/aip_recover_request",
        views.aip_recover_request,
        name="aip_recover_request",
    ),
    re_path(
        r"^packages/(?P<package_uuid>" + UUID + ")/reingest/$",
        views.aip_reingest,
        name="aip_reingest",
    ),
    # Fixity check results
    re_path(
        r"^fixity/(?P<package_uuid>" + UUID + ")/$",
        views.package_fixity,
        name="package_fixity",
    ),
    path("fixity_ajax/", views.fixity_logs_ajax, name="fixity_logs_ajax"),
    # Pipelines
    path("pipelines/", views.pipeline_list, name="pipeline_list"),
    path("pipelines/create/", views.pipeline_edit, name="pipeline_create"),
    re_path(
        r"^pipeline/(?P<uuid>" + UUID + ")/edit/$",
        views.pipeline_edit,
        name="pipeline_edit",
    ),
    re_path(
        r"^pipeline/(?P<uuid>" + UUID + ")/detail/$",
        views.pipeline_detail,
        name="pipeline_detail",
    ),
    re_path(
        r"^pipeline/(?P<uuid>" + UUID + ")/delete/$",
        views.pipeline_delete,
        name="pipeline_delete",
    ),
    re_path(
        r"^pipeline/(?P<uuid>" + UUID + ")/switch_enabled/$",
        views.pipeline_switch_enabled,
        name="pipeline_switch_enabled",
    ),
    # Spaces
    path("spaces/", views.space_list, name="space_list"),
    re_path(
        r"^spaces/(?P<uuid>" + UUID + ")/$", views.space_detail, name="space_detail"
    ),
    re_path(
        r"^spaces/(?P<uuid>" + UUID + ")/edit/$", views.space_edit, name="space_edit"
    ),
    re_path(
        r"^spaces/(?P<uuid>" + UUID + ")/delete/$",
        views.space_delete,
        name="space_delete",
    ),
    re_path(
        r"^spaces/(?P<space_uuid>" + UUID + ")/location_create/$",
        views.location_edit,
        name="location_create",
    ),
    re_path(
        r"^spaces/(?P<space_uuid>"
        + UUID
        + ")/location/(?P<location_uuid>"
        + UUID
        + ")/edit/$",
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
    re_path(
        r"^callbacks/(?P<uuid>" + UUID + ")/$",
        views.callback_detail,
        name="callback_detail",
    ),
    path("callbacks/create/", views.callback_edit, name="callback_create"),
    re_path(
        r"^callbacks/(?P<uuid>" + UUID + ")/edit/$",
        views.callback_edit,
        name="callback_edit",
    ),
    re_path(
        r"^callbacks/(?P<uuid>" + UUID + ")/delete/$",
        views.callback_delete,
        name="callback_delete",
    ),
    re_path(
        r"^callbacks/(?P<uuid>" + UUID + ")/switch_enabled/$",
        views.callback_switch_enabled,
        name="callback_switch_enabled",
    ),
]
