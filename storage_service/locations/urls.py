from django.conf.urls import url
from locations import views

UUID = r"\w{8}-\w{4}-\w{4}-\w{4}-\w{12}"

app_name = "locations"
urlpatterns = [
    # Sorted by alphabetized categories
    # Locations
    url(r"^locations/$", views.location_list, name="location_list"),
    url(
        r"^locations/(?P<location_uuid>" + UUID + ")/$",
        views.location_detail,
        name="location_detail",
    ),
    url(
        r"^locations/(?P<location_uuid>" + UUID + ")/delete/$",
        views.location_delete,
        name="location_delete",
    ),
    url(
        r"^locations/(?P<location_uuid>" + UUID + ")/switch_enabled/$",
        views.location_switch_enabled,
        name="location_switch_enabled",
    ),
    # Packages
    url(r"^packages/$", views.package_list, name="package_list"),
    url(r"^packages_ajax/$", views.package_list_ajax, name="package_list_ajax"),
    url(
        r"^packages/package_delete_request/$",
        views.package_delete_request,
        name="package_delete_request",
    ),
    url(
        r"^packages/(?P<uuid>" + UUID + ")/delete/$",
        views.package_delete,
        name="package_delete",
    ),
    url(
        r"^packages/(?P<uuid>" + UUID + ")/update_status/$",
        views.package_update_status,
        name="package_update_status",
    ),
    url(
        r"^packages/aip_recover_request$",
        views.aip_recover_request,
        name="aip_recover_request",
    ),
    url(
        r"^packages/(?P<package_uuid>" + UUID + ")/reingest/$",
        views.aip_reingest,
        name="aip_reingest",
    ),
    # Fixity check results
    url(
        r"^fixity/(?P<package_uuid>" + UUID + ")/$",
        views.package_fixity,
        name="package_fixity",
    ),
    url(r"^fixity_ajax/$", views.fixity_logs_ajax, name="fixity_logs_ajax"),
    # Pipelines
    url(r"^pipelines/$", views.pipeline_list, name="pipeline_list"),
    url(r"^pipelines/create/$", views.pipeline_edit, name="pipeline_create"),
    url(
        r"^pipeline/(?P<uuid>" + UUID + ")/edit/$",
        views.pipeline_edit,
        name="pipeline_edit",
    ),
    url(
        r"^pipeline/(?P<uuid>" + UUID + ")/detail/$",
        views.pipeline_detail,
        name="pipeline_detail",
    ),
    url(
        r"^pipeline/(?P<uuid>" + UUID + ")/delete/$",
        views.pipeline_delete,
        name="pipeline_delete",
    ),
    url(
        r"^pipeline/(?P<uuid>" + UUID + ")/switch_enabled/$",
        views.pipeline_switch_enabled,
        name="pipeline_switch_enabled",
    ),
    # Spaces
    url(r"^spaces/$", views.space_list, name="space_list"),
    url(r"^spaces/(?P<uuid>" + UUID + ")/$", views.space_detail, name="space_detail"),
    url(r"^spaces/(?P<uuid>" + UUID + ")/edit/$", views.space_edit, name="space_edit"),
    url(
        r"^spaces/(?P<uuid>" + UUID + ")/delete/$",
        views.space_delete,
        name="space_delete",
    ),
    url(
        r"^spaces/(?P<space_uuid>" + UUID + ")/location_create/$",
        views.location_edit,
        name="location_create",
    ),
    url(
        r"^spaces/(?P<space_uuid>"
        + UUID
        + ")/location/(?P<location_uuid>"
        + UUID
        + ")/edit/$",
        views.location_edit,
        name="location_edit",
    ),
    url(r"^spaces/create/$", views.space_create, name="space_create"),
    # Spaces AJAX
    url(
        r"^spaces/get_form_type/$",
        views.ajax_space_create_protocol_form,
        name="ajax_space_create_protocol_form",
    ),
    # Callbacks
    url(r"^callbacks/$", views.callback_list, name="callback_list"),
    url(
        r"^callbacks/(?P<uuid>" + UUID + ")/$",
        views.callback_detail,
        name="callback_detail",
    ),
    url(r"^callbacks/create/$", views.callback_edit, name="callback_create"),
    url(
        r"^callbacks/(?P<uuid>" + UUID + ")/edit/$",
        views.callback_edit,
        name="callback_edit",
    ),
    url(
        r"^callbacks/(?P<uuid>" + UUID + ")/delete/$",
        views.callback_delete,
        name="callback_delete",
    ),
    url(
        r"^callbacks/(?P<uuid>" + UUID + ")/switch_enabled/$",
        views.callback_switch_enabled,
        name="callback_switch_enabled",
    ),
]
