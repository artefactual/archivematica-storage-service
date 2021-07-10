import json
import logging
import os
import requests

from django.contrib import auth, messages
from django.db.models import Q
from django.http import HttpResponse
from django.forms.models import model_to_dict
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import get_template
from django.urls import reverse
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from tastypie.models import ApiKey

from common import decorators
from common import utils
from common import gpgutils
from .models import (
    Callback,
    Space,
    Location,
    Package,
    Event,
    Pipeline,
    LocationPipeline,
    StorageException,
    FixityLog,
    GPG,
)
from . import datatable_utils
from . import forms
from .constants import PROTOCOL

LOGGER = logging.getLogger(__name__)


# ######################## HELPERS ##########################


def get_delete_context_dict(request, model, object_uuid, default_cancel="/"):
    """ Returns a dict of the values needed by the confirm delete view. """
    obj = get_object_or_404(model, uuid=object_uuid)
    header = _("Confirm deleting %(item)s") % {"item": model._meta.verbose_name}
    dependent_objects = utils.dependent_objects(obj)
    if dependent_objects:
        prompt = _(
            "%(item)s cannot be deleted until the following items are also deleted or unassociated."
        ) % {"item": obj}
    else:
        prompt = _("Are you sure you want to delete {item}?") % {"item": obj}
    cancel_url = request.GET.get("next", default_cancel)
    return {
        "header": header,
        "dependent_objects": dependent_objects,
        "prompt": prompt,
        "cancel_url": cancel_url,
    }


# ######################## FILES ##########################


def package_list(request):
    api_key = ApiKey.objects.get(user=request.user).key
    context = {
        "package_count": Package.objects.count(),
        "user": request.user,
        "api_key": api_key,
        "uri": request.build_absolute_uri("/"),
        "redirect_path": request.path,
        "csrf_token": get_token(request),
    }
    return render(request, "locations/package_list.html", context)


def package_list_ajax(request):
    datatable = datatable_utils.PackageDataTable(request.GET)
    data = []
    csrf_token = get_token(request)
    for package in datatable.records:
        data.append(
            get_template("snippets/package_row.html")
            .render(
                {
                    "package": package,
                    "redirect_path": request.META.get("HTTP_REFERER", request.path),
                    "csrf_token": csrf_token,
                }
            )
            .strip()
        )
    # these are the values that DataTables expects from the server
    # see "Reply from the server" in http://legacy.datatables.net/usage/server-side
    response = {
        "iTotalRecords": datatable.total_records,
        "iTotalDisplayRecords": datatable.total_display_records,
        "sEcho": datatable.echo,
        "aaData": data,
    }
    return HttpResponse(
        status=200, content=json.dumps(response), content_type="application/json"
    )


def package_fixity(request, package_uuid):
    log_entries = FixityLog.objects.filter(package__uuid=package_uuid).order_by(
        "-datetime_reported"
    )
    context = {
        "log_entries": log_entries,
        "uri": request.build_absolute_uri("/"),
        "package_uuid": package_uuid,
    }
    return render(request, "locations/fixity_results.html", context)


def fixity_logs_ajax(request):
    datatable = datatable_utils.FixityLogDataTable(request.GET)
    data = []
    for fixity_log in datatable.records:
        data.append(
            get_template("snippets/fixity_log_row.html")
            .render(
                {
                    "entry": fixity_log,
                }
            )
            .strip()
        )
    # these are the values that DataTables expects from the server
    # see "Reply from the server" in http://legacy.datatables.net/usage/server-side
    response = {
        "iTotalRecords": datatable.total_records,
        "iTotalDisplayRecords": datatable.total_display_records,
        "sEcho": datatable.echo,
        "aaData": data,
    }
    return HttpResponse(
        status=200, content=json.dumps(response), content_type="application/json"
    )


class PackageRequestHandlerConfig:
    event_type = ""  # Event type being handled
    approved_status = ""  # Event status, if approved
    reject_message = ""  # Message returned if not approved
    execution_success_message = ""  # Message returned if execution success
    execution_fail_message = ""  # Message returned if execution failed

    def execution_logic(package):  # Logic performed on package if approved
        pass


def aip_recover_request(request):
    def execution_logic(aip):
        recover_location = LocationPipeline.objects.get(
            pipeline=aip.origin_pipeline, location__purpose=Location.AIP_RECOVERY
        ).location

        try:
            (success, _, message) = aip.recover_aip(
                recover_location, os.path.basename(aip.current_path)
            )
        except StorageException:
            recover_path = os.path.join(
                recover_location.full_path(), os.path.basename(aip.full_path())
            )
            message = _("error accessing restore files at %(path)s") % {
                "path": recover_path
            }
            success = False

        return (success, message)

    config = PackageRequestHandlerConfig()
    config.event_type = Event.RECOVER
    config.approved_status = Package.UPLOADED
    config.reject_message = _("AIP restore rejected.")
    config.execution_success_message = _("AIP restored.")
    config.execution_fail_message = _("AIP restore failed")
    config.execution_logic = execution_logic

    return _handle_package_request(request, config, "locations:aip_recover_request")


@require_http_methods(["POST"])
def package_delete(request, uuid):
    """Delete packages without extra approval requirement.

    This is limited to packages listed in
    ``PACKAGE_TYPE_CAN_DELETE_DIRECTLY``.
    """
    package = get_object_or_404(Package, uuid=uuid)
    package_list_url = reverse("locations:package_list")

    def respond(tag, message):
        try:
            message_method = getattr(messages, tag)
        except AttributeError:
            return
        message_method(request, message)
        return redirect(package_list_url)

    if package.package_type not in package.PACKAGE_TYPE_CAN_DELETE_DIRECTLY:
        return respond(
            "error",
            _(
                "Package of type %(type)s cannot be deleted"
                " directly" % {"type": package.package_type}
            ),
        )
    errmsg = _(
        "Package deletion failed. Please contact an administrator or"
        " see logs for details."
    )
    try:
        ok, err = package.delete_from_storage()
    except Exception:
        LOGGER.exception("Package deletion failed")
        return respond("error", errmsg)
    if not ok:
        LOGGER.error("Package deletion failed: %s", err)
        return respond("error", errmsg)
    return respond("success", _("Package deleted successfully!"))


def package_delete_request(request):
    def execution_logic(package):
        return package.delete_from_storage()

    config = PackageRequestHandlerConfig()
    config.event_type = Event.DELETE
    config.approved_status = Package.DELETED
    config.reject_message = _("Request rejected, package still stored.")
    config.execution_success_message = _("Package deleted successfully.")
    config.execution_fail_message = _("Package was not deleted from disk correctly")
    config.execution_logic = execution_logic

    return _handle_package_request(request, config, "locations:package_delete_request")


def _handle_package_request(request, config, view_name):
    request_events = Event.objects.filter(status=Event.SUBMITTED).filter(
        event_type=config.event_type
    )

    if request.method == "POST":
        # FIXME won't scale with many pending deletes, since does linear search
        # on all the forms
        for req in request_events:
            req.form = forms.ConfirmEventForm(
                request.POST, prefix=str(req.id), instance=req
            )
            if req.form.is_valid():
                event = req.form.save()
                event.status_reason = req.form.cleaned_data["status_reason"]
                event.admin_id = auth.get_user(request)
                # Handle administrator decision and optionally notify remote REST endpoint
                if "reject" in request.POST:
                    event.status = Event.REJECTED
                    # Request is rejected so the package status set back to
                    # what it was stored as previously.
                    event.package.status = event.store_data
                    notification_message = (
                        _handle_package_request_remote_result_notification(
                            config, event, False
                        )
                    )
                    if notification_message:
                        config.reject_message += " " + notification_message
                    messages.success(request, config.reject_message)
                elif "approve" in request.POST:
                    event.status = Event.APPROVED
                    success, err_msg = config.execution_logic(event.package)
                    if not success:
                        error_message = "{}: {}. {}".format(
                            config.execution_fail_message,
                            err_msg,
                            _(
                                "Please contact an administrator or see logs for details."
                            ),
                        )
                        notification_message = (
                            _handle_package_request_remote_result_notification(
                                config, event, False
                            )
                        )
                        if notification_message:
                            error_message += " " + notification_message
                        messages.error(request, error_message)
                    else:
                        # Package deletion was a success so update the package
                        # status per the event.
                        event.package.status = config.approved_status
                        approval_message = _("Request approved: %(message)s") % {
                            "message": config.execution_success_message
                        }
                        notification_message = (
                            _handle_package_request_remote_result_notification(
                                config, event, True
                            )
                        )
                        if notification_message:
                            approval_message += " " + notification_message
                        messages.success(request, approval_message)
                        if err_msg:
                            messages.info(request, err_msg)
                event.save()
                event.package.save()
                return redirect(view_name)
    else:
        for req in request_events:
            req.form = forms.ConfirmEventForm(prefix=str(req.id), instance=req)

    closed_requests = Event.objects.filter(
        Q(status=Event.APPROVED) | Q(status=Event.REJECTED)
    )

    return render(request, "locations/package_request.html", locals())


def _handle_package_request_remote_result_notification(config, event, success):
    response_message = None

    # Setting name is determined using event type
    setting_prefix = f"{config.event_type.lower()}_request_notification"
    request_notification_url = utils.get_setting(f"{setting_prefix}_url")

    # If notification is configured, attempt
    if request_notification_url is not None:
        headers = {"Content-type": "application/json"}

        # Status reported may be approved, yet failed during execution
        status_to_report = event.status
        if event.status == Event.APPROVED and not success:
            status_to_report += " (failed)"

        # Serialize payload
        payload = json.dumps(
            {
                "event_id": event.id,
                "message": f"{status_to_report}: {event.status_reason}",
                "success": success,
            }
        )

        # Specify basic authentication, if configured
        request_notification_auth_username = utils.get_setting(
            f"{setting_prefix}_auth_username"
        )
        request_notification_auth_password = utils.get_setting(
            f"{setting_prefix}_auth_password"
        )

        if request_notification_auth_username is not None:
            auth = requests.auth.HTTPBasicAuth(
                request_notification_auth_username, request_notification_auth_password
            )
        else:
            auth = None

        # Make request and set response message, if included in notification request response body
        notification_response = requests.post(
            request_notification_url, auth=auth, data=payload, headers=headers
        )
        try:
            responseData = json.loads(notification_response.content)
            response_message = responseData["message"]
        except ValueError:
            pass

    return response_message


def package_update_status(request, uuid):
    package = Package.objects.get(uuid=uuid)

    old_status = package.status
    try:
        (new_status, error) = package.current_location.space.update_package_status(
            package
        )
    except Exception:
        LOGGER.exception("update status")
        new_status = None
        error = _("Error getting status for package %(uuid)s") % {"uuid": uuid}

    if new_status is not None:
        if old_status != new_status:
            messages.info(
                request,
                _("Status for package %(package)s is now %(status)s'.")
                % {"package": uuid, "status": package.get_status_display()},
            )
        else:
            messages.info(
                request,
                _("Status for package %(uuid)s has not changed.") % {"uuid": uuid},
            )

    if error:
        messages.warning(request, error)

    next_url = request.GET.get("next", reverse("locations:package_list"))
    return redirect(next_url)


def aip_reingest(request, package_uuid):
    next_url = request.GET.get("next", reverse("locations:package_list"))
    try:
        package = Package.objects.get(uuid=package_uuid)
    except Package.DoesNotExist:
        messages.warning(
            request,
            _("Package with UUID %(uuid)s does not exist.") % {"uuid": package_uuid},
        )
        return redirect(next_url)
    if package.replicated_package:
        messages.warning(
            request,
            _("Package %(uuid)s is a replica and replicas cannot be re-ingested.")
            % {"uuid": package_uuid},
        )
        return redirect(next_url)
    form = forms.ReingestForm(request.POST or None)
    if form.is_valid():
        pipeline = form.cleaned_data["pipeline"]
        reingest_type = form.cleaned_data["reingest_type"]
        processing_config = form.cleaned_data.get("processing_config", "default")
        response = package.start_reingest(pipeline, reingest_type, processing_config)
        error = response.get("error", True)
        message = response.get("message", _("An unknown error occurred"))
        if not error:
            if message:
                messages.success(request, message)
        else:
            messages.warning(request, message)
        return redirect(next_url)
    return render(request, "locations/package_reingest.html", locals())


# ####################### LOCATIONS ##########################


def location_edit(request, space_uuid, location_uuid=None):
    space = get_object_or_404(Space, uuid=space_uuid)
    if location_uuid:
        action = _("Edit Location")
        location = get_object_or_404(Location, uuid=location_uuid)
    else:
        action = _("Create Location")
        location = None
    form = forms.LocationForm(
        request.POST or None, space_protocol=space.access_protocol, instance=location
    )

    if form.is_valid():
        location = form.save(commit=False)
        location.space = space
        location.save()
        # Cannot use form.save_m2m() because of 'through' table
        for pipeline in form.cleaned_data["pipeline"]:
            LocationPipeline.objects.get_or_create(location=location, pipeline=pipeline)
        location.replicators.clear()
        for replicator_loc in form.cleaned_data["replicators"]:
            location.replicators.add(replicator_loc)
        # Delete relationships between the location and pipelines not in the form
        to_delete = LocationPipeline.objects.filter(location=location).exclude(
            pipeline__in=list(form.cleaned_data["pipeline"])
        )
        # NOTE Need to convert form.cleaned_data['pipeline'] to a list, or the
        # SQL generated by pipeline__in is garbage in Django 1.5.
        LOGGER.debug("LocationPipeline to delete: %s", to_delete)
        to_delete.delete()
        messages.success(request, _("Location saved."))
        # TODO make this return to the originating page
        # http://stackoverflow.com/questions/4203417/django-how-do-i-redirect-to-page-where-form-originated
        return redirect("locations:location_detail", location.uuid)
    return render(request, "locations/location_form.html", locals())


def location_list(request):
    locations = Location.objects.all()
    return render(request, "locations/location_list.html", locals())


def location_detail(request, location_uuid):
    try:
        location = Location.objects.get(uuid=location_uuid)
    except Location.DoesNotExist:
        messages.warning(
            request, _("Location %(uuid)s does not exist.") % {"uuid": location_uuid}
        )
        return redirect("locations:location_list")
    pipelines = Pipeline.objects.filter(location=location)
    package_count = Package.objects.filter(current_location=location).count()
    return render(request, "locations/location_detail.html", locals())


def location_switch_enabled(request, location_uuid):
    location = get_object_or_404(Location, uuid=location_uuid)
    location.enabled = not location.enabled
    location.save()
    next_url = request.GET.get(
        "next", reverse("locations:location_detail", args=[location.uuid])
    )
    return redirect(next_url)


def location_delete_context(request, location_uuid):
    return get_delete_context_dict(
        request, Location, location_uuid, reverse("locations:location_list")
    )


@decorators.confirm_required("locations/delete.html", location_delete_context)
def location_delete(request, location_uuid):
    location = get_object_or_404(Location, uuid=location_uuid)
    location.delete()
    next_url = request.GET.get("next", reverse("locations:location_list"))
    return redirect(next_url)


# ######################## PIPELINES ##########################


def pipeline_edit(request, uuid=None):
    if uuid:
        action = _("Edit Pipeline")
        pipeline = get_object_or_404(Pipeline, uuid=uuid)
        initial = {}
    else:
        action = _("Create Pipeline")
        pipeline = None
        initial = {
            "create_default_locations": True,
            "enabled": not utils.get_setting("pipelines_disabled"),
        }

    if request.method == "POST":
        form = forms.PipelineForm(request.POST, instance=pipeline, initial=initial)
        if form.is_valid():
            pipeline = form.save()
            pipeline.save(form.cleaned_data["create_default_locations"])
            messages.success(request, _("Pipeline saved."))
            return redirect("locations:pipeline_list")
    else:
        form = forms.PipelineForm(instance=pipeline, initial=initial)
    return render(
        request,
        "locations/pipeline_form.html",
        {
            "action": action,
            "form": form,
            "pipeline": pipeline,
        },
    )


def pipeline_list(request):
    pipelines = Pipeline.objects.all()
    return render(request, "locations/pipeline_list.html", locals())


def pipeline_detail(request, uuid):
    try:
        pipeline = Pipeline.objects.get(uuid=uuid)
    except Pipeline.DoesNotExist:
        messages.warning(
            request, _("Pipeline %(uuid)s does not exist.") % {"uuid": uuid}
        )
        return redirect("locations:pipeline_list")
    locations = Location.objects.filter(pipeline=pipeline)
    return render(request, "locations/pipeline_detail.html", locals())


def pipeline_switch_enabled(request, uuid):
    pipeline = get_object_or_404(Pipeline, uuid=uuid)
    pipeline.enabled = not pipeline.enabled
    pipeline.save()
    next_url = request.GET.get(
        "next", reverse("locations:pipeline_detail", args=[pipeline.uuid])
    )
    return redirect(next_url)


def pipeline_delete_context(request, uuid):
    return get_delete_context_dict(
        request, Pipeline, uuid, reverse("locations:pipeline_list")
    )


@decorators.confirm_required("locations/delete.html", pipeline_delete_context)
def pipeline_delete(request, uuid):
    pipeline = get_object_or_404(Pipeline, uuid=uuid)
    pipeline.delete()
    next_url = request.GET.get("next", reverse("locations:pipeline_list"))
    return redirect(next_url)


# ######################## SPACES ##########################


def space_list(request):
    spaces = Space.objects.all()

    def add_child(space):
        model = PROTOCOL[space.access_protocol]["model"]
        child = model.objects.get(space=space)
        child_dict_raw = model_to_dict(
            child, PROTOCOL[space.access_protocol]["fields"] or [""]
        )
        child_dict = {
            child._meta.get_field(field).verbose_name: value
            for field, value in child_dict_raw.items()
        }
        space.child = child_dict

    list(map(add_child, spaces))
    return render(request, "locations/space_list.html", locals())


def space_detail(request, uuid):
    try:
        space = Space.objects.get(uuid=uuid)
    except Space.DoesNotExist:
        messages.warning(request, _("Space %(uuid)s does not exist.") % {"uuid": uuid})
        return redirect("locations:space_list")
    child = space.get_child_space()

    child_dict_raw = model_to_dict(
        child, PROTOCOL[space.access_protocol]["fields"] or [""]
    )
    child_dict = {
        child._meta.get_field(field).verbose_name: get_child_space_value(
            value, field, child
        )
        for field, value in child_dict_raw.items()
    }
    space.child = child_dict
    locations = Location.objects.filter(space=space)
    return render(request, "locations/space_detail.html", locals())


def get_child_space_value(value, field, child):
    """If the child space ``child`` is a GPG instance, and the field is key, we
    return a human-readable representation of the GPG key instead of its
    fingerprint: the name of the first user in its uids list.
    """
    if field == "key" and isinstance(child, GPG):
        key = gpgutils.get_gpg_key(value)
        return " ".join(key["uids"][0].split()[:-1])
    return value


def space_create(request):
    if request.method == "POST":
        space_form = forms.SpaceForm(request.POST, prefix="space")
        if space_form.is_valid():
            # Get access protocol form to validate
            access_protocol = space_form.cleaned_data["access_protocol"]
            protocol_form = PROTOCOL[access_protocol]["form"](
                request.POST, prefix="protocol"
            )
            if protocol_form.is_valid():
                # If both are valid, save everything
                space = space_form.save()
                protocol_obj = protocol_form.save(commit=False)
                protocol_obj.space = space
                protocol_obj.save()
                messages.success(request, _("Space saved."))
                return redirect("locations:space_detail", space.uuid)
        else:
            # We need to return the protocol_form so that protocol_form errors
            # are displayed, and so the form doesn't mysterious disappear
            # See if access_protocol has been set
            access_protocol = space_form["access_protocol"].value()
            if access_protocol:
                protocol_form = PROTOCOL[access_protocol]["form"](
                    request.POST, prefix="protocol"
                )
    else:
        space_form = forms.SpaceForm(prefix="space")

    return render(request, "locations/space_form.html", locals())


def space_edit(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    protocol_space = space.get_child_space()
    space_form = forms.SpaceForm(request.POST or None, prefix="space", instance=space)
    protocol_form = PROTOCOL[space.access_protocol]["form"](
        request.POST or None, prefix="protocol", instance=protocol_space
    )
    if space_form.is_valid() and protocol_form.is_valid():
        space_form.save()
        protocol_form.save()
        messages.success(request, _("Space saved."))
        return redirect("locations:space_detail", space.uuid)
    return render(request, "locations/space_edit.html", locals())


# FIXME this should probably submit a csrf token
@csrf_exempt
def ajax_space_create_protocol_form(request):
    """ Return a protocol-specific form, based on the input protocol. """
    if request.method == "POST":
        sent_protocol = request.POST.get("protocol")
        try:
            # Get form class if it exists
            form_class = PROTOCOL[sent_protocol]["form"]
        except KeyError:
            response_data = {}
        else:
            # Create and return the form
            form = form_class(prefix="protocol")
            response_data = form.as_p()
    return HttpResponse(response_data, content_type="text/html")


def space_delete_context(request, uuid):
    return get_delete_context_dict(
        request, Space, uuid, reverse("locations:space_list")
    )


@decorators.confirm_required("locations/delete.html", space_delete_context)
def space_delete(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    space.delete()
    next_url = request.GET.get("next", reverse("locations:space_list"))
    return redirect(next_url)


# ######################## CALLBACKS ##########################


def callback_detail(request, uuid):
    try:
        callback = Callback.objects.get(uuid=uuid)
    except Callback.DoesNotExist:
        messages.warning(
            request, _("Callback %(uuid)s does not exist.") % {"uuid": uuid}
        )
        return redirect("locations:callback_list")
    return render(request, "locations/callback_detail.html", locals())


def callback_switch_enabled(request, uuid):
    callback = get_object_or_404(Callback, uuid=uuid)
    callback.enabled = not callback.enabled
    callback.save()
    next_url = request.GET.get(
        "next", reverse("locations:callback_detail", args=[callback.uuid])
    )
    return redirect(next_url)


def callback_list(request):
    callbacks = Callback.objects.all()
    return render(request, "locations/callback_list.html", locals())


def callback_edit(request, uuid=None):
    if uuid:
        action = _("Edit Callback")
        callback = get_object_or_404(Callback, uuid=uuid)
    else:
        action = _("Create Callback")
        callback = None

    form = forms.CallbackForm(request.POST or None, instance=callback)
    if form.is_valid():
        callback = form.save()
        messages.success(request, _("Callback saved."))
        return redirect("locations:callback_detail", callback.uuid)
    return render(request, "locations/callback_form.html", locals())


def callback_delete(request, uuid):
    callback = get_object_or_404(Callback, uuid=uuid)
    callback.delete()
    next_url = request.GET.get("next", reverse("locations:callback_list"))
    return redirect(next_url)
