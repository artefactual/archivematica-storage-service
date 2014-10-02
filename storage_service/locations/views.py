import json
import logging
import os
import requests

from django.contrib import auth, messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse
from django.forms.models import model_to_dict
from django.shortcuts import render, redirect, get_object_or_404
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt

from common import decorators
from common import utils
from .models import Callback, Space, Location, Package, Event, Pipeline, LocationPipeline, StorageException
from . import forms
from .constants import PROTOCOL

LOGGER = logging.getLogger(__name__)


########################## HELPERS ##########################

def get_delete_context_dict(request, model, object_uuid, default_cancel='/'):
    """ Returns a dict of the values needed by the confirm delete view. """
    obj = get_object_or_404(model, uuid=object_uuid)
    header = "Confirm deleting {}".format(model._meta.verbose_name)
    dependent_objects = utils.dependent_objects(obj)
    if dependent_objects:
        prompt = "{} cannot be deleted until the following items are also deleted or unassociated.".format(obj)
    else:
        prompt = "Are you sure you want to delete {}?".format(obj)
    cancel_url = request.GET.get('next', default_cancel)
    return {
        'header': header,
        'dependent_objects': dependent_objects,
        'prompt': prompt,
        'cancel_url': cancel_url,
    }

########################## FILES ##########################

def package_list(request):
    packages = Package.objects.all()
    return render(request, 'locations/package_list.html', locals())

def aip_recover_request(request):
    def execution_logic(aip): 
        recover_location = LocationPipeline.objects.get(
            pipeline=aip.origin_pipeline, location__purpose=Location.AIP_RECOVERY).location

        try:
            (success, failures, message) = aip.recover_aip(
                recover_location, os.path.basename(aip.current_path))
        except StorageException:
            recover_path = os.path.join(recover_location.full_path(), os.path.basename(aip.full_path()))
            message = 'error accessing restore files at {}'.format(recover_path)
            success = False

        return (success, message)

    config = AIPRequestHandlerConfig()
    config.event_type = Event.RECOVER
    config.approved_status = Package.UPLOADED
    config.reject_message = 'AIP restore rejected.'
    config.execution_success_message = 'AIP restored.'
    config.execution_fail_message = 'AIP restore failed'
    config.execution_logic = execution_logic

    return _handle_aip_request(request, config, 'aip_recover_request')

def aip_delete_request(request):
    def execution_logic(aip): 
        return aip.delete_from_storage()

    config = AIPRequestHandlerConfig()
    config.event_type = Event.DELETE
    config.approved_status = Package.DELETED
    config.reject_message = 'Request rejected, package still stored.'
    config.execution_success_message = 'Package deleted successfully.'
    config.execution_fail_message = 'Package was not deleted from disk correctly'
    config.execution_logic = execution_logic

    return _handle_aip_request(request, config, 'aip_delete_request')

def _handle_aip_request(request, config, view_name):
    request_events = Event.objects.filter(status=Event.SUBMITTED).filter(
        event_type=config.event_type)

    if request.method == 'POST':
        # FIXME won't scale with many pending deletes, since does linear search
        # on all the forms
        for req in request_events:
            req.form = forms.ConfirmEventForm(request.POST, prefix=str(req.id),
                instance=req)
            if req.form.is_valid():
                event = req.form.save()
                event.status_reason = req.form.cleaned_data['status_reason']
                event.admin_id = auth.get_user(request)

                # Handle administrator decision and optionally notify remote REST endpoint
                if 'reject' in request.POST:
                    event.status = Event.REJECTED
                    event.package.status = event.store_data
                    notification_message = _handle_aip_request_remote_result_notification(config, event, False)
                    if notification_message:
                        config.reject_message += ' ' + notification_message
                    messages.success(request, config.reject_message)
                elif 'approve' in request.POST:
                    event.status = Event.APPROVED
                    event.package.status = config.approved_status
                    success, err_msg = config.execution_logic(event.package)
                    if not success:
                        error_message = "{}: {}. Please contact an administrator or see logs for details.".format(
                            config.execution_fail_message, err_msg)
                        notification_message = _handle_aip_request_remote_result_notification(config, event, False)
                        if notification_message:
                            error_message += ' ' + notification_message
                        messages.error(request, error_message)
                    else:
                        approval_message = "Request approved. {}".format(config.execution_success_message)
                        notification_message = _handle_aip_request_remote_result_notification(config, event, True)
                        if notification_message:
                            approval_message += ' ' + notification_message
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
        Q(status=Event.APPROVED) | Q(status=Event.REJECTED))

    return render(request, 'locations/aip_request.html', locals())

def _handle_aip_request_remote_result_notification(config, event, success):
    response_message = None

    # Setting name is determined using event type
    setting_prefix = "{}_request_notification".format(config.event_type.lower())
    request_notification_url = utils.get_setting("{}_url".format(setting_prefix))

    # If notification is configured, attempt
    if request_notification_url != None:
        headers = {"Content-type": "application/json"}

        # Status reported may be approved, yet failed during execution
        status_to_report = event.status
        if event.status == Event.APPROVED and not success:
            status_to_report += ' (failed)'

        # Serialize payload
        payload = json.dumps({
            "event_id": event.id,
            "message": "{}: {}".format(status_to_report, event.status_reason),
            "success": success
        })

        # Specify basic authentication, if configured
        request_notification_auth_username = utils.get_setting("{}_auth_username".format(setting_prefix))
        request_notification_auth_password = utils.get_setting("{}_auth_password".format(setting_prefix))

        if request_notification_auth_username != None:
            auth = requests.auth.HTTPBasicAuth(request_notification_auth_username, request_notification_auth_password)
        else:
            auth = None

        # Make request and set response message, if included in notification request response body
        notification_response = requests.post(request_notification_url, auth=auth, data=payload, headers=headers)
        try:
            responseData = json.loads(notification_response.content)
            response_message = responseData['message']
        except ValueError:
            pass

    return response_message

def package_update_status(request, uuid):
    package = Package.objects.get(uuid=uuid)

    old_status = package.status
    try:
        (new_status, error) = package.current_location.space.update_package_status(package)
    except Exception:
        LOGGER.exception('update status')
        new_status = None
        error = 'Error getting status for package {}'.format(uuid)

    if new_status is not None:
        if old_status != new_status:
            messages.info(request,
                "Status for package {} is now '{}'.".format(uuid, package.get_status_display()))
        else:
            messages.info(request,
                'Status for package {} has not changed.'.format(uuid))

    if error:
        messages.warning(request, error)

    next_url = request.GET.get('next', reverse('package_list'))
    return redirect(next_url)

class AIPRequestHandlerConfig:
    event_type = ''                # Event type being handled
    approved_status = ''           # Event status, if approved
    reject_message = ''            # Message returned if not approved
    execution_success_message = '' # Message returned if execution success
    execution_fail_message = ''    # Message returned if execution failed

    def execution_logic(package):  # Logic performed on package if approved
        pass


########################## LOCATIONS ##########################

def location_edit(request, space_uuid, location_uuid=None):
    space = get_object_or_404(Space, uuid=space_uuid)
    if location_uuid:
        action = "Edit"
        location = get_object_or_404(Location, uuid=location_uuid)
    else:
        action = "Create"
        location = None
    form = forms.LocationForm(request.POST or None, space_protocol=space.access_protocol, instance=location)
    if form.is_valid():
        location = form.save(commit=False)
        location.space = space
        location.save()
        # Cannot use form.save_m2m() because of 'through' table
        for pipeline in form.cleaned_data['pipeline']:
            LocationPipeline.objects.get_or_create(
                location=location, pipeline=pipeline)

        # Delete relationships between the location and pipelines not in the form
        to_delete = LocationPipeline.objects.filter(location=location).exclude(
            pipeline__in=list(form.cleaned_data['pipeline']))
        # NOTE Need to convert form.cleaned_data['pipeline'] to a list, or the
        # SQL generated by pipeline__in is garbage in Django 1.5.
        LOGGER.debug("LocationPipeline to delete: %s", to_delete)
        to_delete.delete()
        messages.success(request, "Location saved.")
        # TODO make this return to the originating page
        # http://stackoverflow.com/questions/4203417/django-how-do-i-redirect-to-page-where-form-originated
        return redirect('location_detail', location.uuid)
    return render(request, 'locations/location_form.html', locals())

def location_list(request):
    locations = Location.objects.all()
    return render(request, 'locations/location_list.html', locals())

def location_detail(request, location_uuid):
    try:
        location = Location.objects.get(uuid=location_uuid)
    except Location.DoesNotExist:
        messages.warning(request, "Location {} does not exist.".format(location_uuid))
        return redirect('location_list')
    pipelines = Pipeline.objects.filter(location=location)
    packages = Package.objects.filter(current_location=location)
    return render(request, 'locations/location_detail.html', locals())

def location_switch_enabled(request, location_uuid):
    location = get_object_or_404(Location, uuid=location_uuid)
    location.enabled = not location.enabled
    location.save()
    next_url = request.GET.get('next', reverse('location_detail', args=[location.uuid]))
    return redirect(next_url)

def location_delete_context(request, location_uuid):
    context_dict = get_delete_context_dict(request, Location, location_uuid,
        reverse('location_list'))
    return RequestContext(request, context_dict)

@decorators.confirm_required('locations/delete.html', location_delete_context)
def location_delete(request, location_uuid):
    location = get_object_or_404(Location, uuid=location_uuid)
    location.delete()
    next_url = request.GET.get('next', reverse('location_list'))
    return redirect(next_url)


########################## PIPELINES ##########################

def pipeline_edit(request, uuid=None):
    if uuid:
        action = "Edit"
        pipeline = get_object_or_404(Pipeline, uuid=uuid)
        initial = {}
    else:
        action = "Create"
        pipeline = None
        initial = {'enabled': not utils.get_setting('pipelines_disabled')}

    if request.method == 'POST':
        form = forms.PipelineForm(request.POST, instance=pipeline, initial=initial)
        if form.is_valid():
            pipeline = form.save()
            pipeline.save(form.cleaned_data['create_default_locations'])
            messages.success(request, "Pipeline saved.")
            return redirect('pipeline_list')
    else:
        form = forms.PipelineForm(instance=pipeline, initial=initial)
    return render(request, 'locations/pipeline_form.html', locals())

def pipeline_list(request):
    pipelines = Pipeline.objects.all()
    return render(request, 'locations/pipeline_list.html', locals())

def pipeline_detail(request, uuid):
    try:
        pipeline = Pipeline.objects.get(uuid=uuid)
    except Pipeline.DoesNotExist:
        messages.warning(request, "Pipeline {} does not exist.".format(uuid))
        return redirect('pipeline_list')
    locations = Location.objects.filter(pipeline=pipeline)
    return render(request, 'locations/pipeline_detail.html', locals())

def pipeline_switch_enabled(request, uuid):
    pipeline = get_object_or_404(Pipeline, uuid=uuid)
    pipeline.enabled = not pipeline.enabled
    pipeline.save()
    next_url = request.GET.get('next', reverse('pipeline_detail', args=[pipeline.uuid]))
    return redirect(next_url)

def pipeline_delete_context(request, uuid):
    context_dict = get_delete_context_dict(request, Pipeline, uuid,
        reverse('pipeline_list'))
    return RequestContext(request, context_dict)

@decorators.confirm_required('locations/delete.html', pipeline_delete_context)
def pipeline_delete(request, uuid):
    pipeline = get_object_or_404(Pipeline, uuid=uuid)
    pipeline.delete()
    next_url = request.GET.get('next', reverse('pipeline_list'))
    return redirect(next_url)

########################## SPACES ##########################

def space_list(request):
    spaces = Space.objects.all()

    def add_child(space):
        model = PROTOCOL[space.access_protocol]['model']
        child = model.objects.get(space=space)
        child_dict_raw = model_to_dict(child,
            PROTOCOL[space.access_protocol]['fields'] or [''])
        child_dict = { child._meta.get_field_by_name(field)[0].verbose_name: value
            for field, value in child_dict_raw.iteritems() }
        space.child = child_dict
    map(add_child, spaces)
    return render(request, 'locations/space_list.html', locals())

def space_detail(request, uuid):
    try:
        space = Space.objects.get(uuid=uuid)
    except Space.DoesNotExist:
        messages.warning(request, "Space {} does not exist.".format(uuid))
        return redirect('space_list')
    child = space.get_child_space()

    child_dict_raw = model_to_dict(child,
        PROTOCOL[space.access_protocol]['fields']or [''])
    child_dict = { child._meta.get_field_by_name(field)[0].verbose_name: value
        for field, value in child_dict_raw.iteritems() }
    space.child = child_dict
    locations = Location.objects.filter(space=space)
    return render(request, 'locations/space_detail.html', locals())

def space_create(request):
    if request.method == 'POST':
        space_form = forms.SpaceForm(request.POST, prefix='space')
        if space_form.is_valid():
            # Get access protocol form to validate
            access_protocol = space_form.cleaned_data['access_protocol']
            protocol_form = PROTOCOL[access_protocol]['form'](
                request.POST, prefix='protocol')
            if protocol_form.is_valid():
                # If both are valid, save everything
                space = space_form.save()
                protocol_obj = protocol_form.save(commit=False)
                protocol_obj.space = space
                protocol_obj.save()
                messages.success(request, "Space saved.")
                return redirect('space_detail', space.uuid)
        else:
            # We need to return the protocol_form so that protocol_form errors
            # are displayed, and so the form doesn't mysterious disappear
            # See if access_protocol has been set
            access_protocol = space_form['access_protocol'].value()
            if access_protocol:
                protocol_form = PROTOCOL[access_protocol]['form'](
                   request.POST, prefix='protocol')
    else:
        space_form = forms.SpaceForm(prefix='space')

    return render(request, 'locations/space_form.html', locals())

def space_edit(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    protocol_space = space.get_child_space()
    space_form = forms.SpaceForm(request.POST or None, prefix='space', instance=space)
    protocol_form = PROTOCOL[space.access_protocol]['form'](
                request.POST or None, prefix='protocol', instance=protocol_space)
    if space_form.is_valid() and protocol_form.is_valid():
        space_form.save()
        protocol_form.save()
        messages.success(request, "Space saved.")
        return redirect('space_detail', space.uuid)
    return render(request, 'locations/space_edit.html', locals())

# FIXME this should probably submit a csrf token
@csrf_exempt
def ajax_space_create_protocol_form(request):
    """ Return a protocol-specific form, based on the input protocol. """
    if request.method == "POST":
        sent_protocol = request.POST.get("protocol")
        try:
            # Get form class if it exists
            form_class = PROTOCOL[sent_protocol]['form']
        except KeyError:
            response_data = {}
        else:
            # Create and return the form
            form = form_class(prefix='protocol')
            response_data = form.as_p()
    return HttpResponse(response_data, content_type="text/html")

def space_delete_context(request, uuid):
    context_dict = get_delete_context_dict(request, Space, uuid,
        reverse('space_list'))
    return RequestContext(request, context_dict)

@decorators.confirm_required('locations/delete.html', space_delete_context)
def space_delete(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    space.delete()
    next_url = request.GET.get('next', reverse('space_list'))
    return redirect(next_url)

########################## CALLBACKS ##########################

def callback_detail(request, uuid):
    try:
        callback = Callback.objects.get(uuid=uuid)
    except Callback.DoesNotExist:
        messages.warning(request, "Callback {} does not exist.".format(location_uuid))
        return redirect('callback_list')
    return render(request, 'locations/callback_detail.html', locals())

def callback_switch_enabled(request, uuid):
    callback = get_object_or_404(Callback, uuid=uuid)
    callback.enabled = not callback.enabled
    callback.save()
    next_url = request.GET.get('next', reverse('callback_detail', args=[callback.uuid]))
    return redirect(next_url)

def callback_list(request):
    callbacks = Callback.objects.all()
    return render(request, 'locations/callback_list.html', locals())

def callback_edit(request, uuid=None):
    if uuid:
        action = "Edit"
        callback = get_object_or_404(Callback, uuid=uuid)
    else:
        action = "Create"
        callback = None

    form = forms.CallbackForm(request.POST or None, instance=callback)
    if form.is_valid():
        callback = form.save()
        messages.success(request, "Callback saved.")
        return redirect('callback_detail', callback.uuid)
    return render(request, 'locations/callback_form.html', locals())

def callback_delete(request, uuid):
    callback = get_object_or_404(Callback, uuid=uuid)
    callback.delete()
    next_url = request.GET.get('next', reverse('callback_list'))
    return redirect(next_url)
