
from django.contrib import auth
from django.db.models import Q
from django.http import HttpResponse
from django.forms.models import model_to_dict
from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.views.decorators.csrf import csrf_exempt

from common.constants import PROTOCOL
from .models import Space, Location, File, Event, Pipeline
from .forms import SpaceForm, LocationForm, ConfirmEventForm, PipelineForm


########################## FILES ##########################

def file_list(request):
    files = File.objects.all()
    return render(request, 'locations/file_list.html', locals())

def aip_delete_request(request):
    requests = Event.objects.filter(status=Event.SUBMITTED).filter(
        event_type=Event.DELETE)
    if request.method == 'POST':
        # FIXME won't scale with many pending deletes, since does linear search
        # on all the forms
        for req in requests:
            req.form = ConfirmEventForm(request.POST, prefix=str(req.id),
                instance=req)
            if req.form.is_valid():
                event = req.form.save()
                event.status_reason = req.form.cleaned_data['status_reason']
                event.admin_id = auth.get_user(request)
                if 'reject' in request.POST:
                    event.status = Event.REJECTED
                    event.file.status = event.store_data
                elif 'approve' in request.POST:
                    event.status = Event.APPROVED
                    event.file.status = File.DELETED
                    # TODO do actual deletion here
                event.save()
                event.file.save()
                return redirect('aip_delete_request')
    else:
        for req in requests:
            req.form = ConfirmEventForm(prefix=str(req.id), instance=req)
    closed_requests = Event.objects.filter(
        Q(status=Event.APPROVED) | Q(status=Event.REJECTED))
    return render(request, 'locations/aip_delete_request.html', locals())


########################## LOCATIONS ##########################

def location_create(request, space_uuid):
    space = get_object_or_404(Space, uuid=space_uuid)
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save(commit=False)
            location.space = space
            location.save()
            return redirect('space_detail', space.uuid)
    else:
        form = LocationForm()
    return render(request, 'locations/location_form.html', locals())

def location_list(request):
    locations = Location.enabled.all()
    # TODO sort by purpose?  Or should that be done in the template?
    return render(request, 'locations/location_list.html', locals())


########################## PIPELINES ##########################

def pipeline_edit(request, uuid=None):
    if uuid:
        action = "Edit"
        pipeline = get_object_or_404(Pipeline, uuid=uuid)
    else:
        action = "Create"
        pipeline = None

    if request.method == 'POST':
        form = PipelineForm(request.POST, instance=pipeline)
        if form.is_valid():
            form.save()
            return redirect('pipeline_list')
    else:
        form = PipelineForm(instance=pipeline)
    return render(request, 'locations/pipeline_form.html', locals())


def pipeline_list(request):
    pipelines = Pipeline.objects.all()
    return render(request, 'locations/pipeline_list.html', locals())


########################## SPACES ##########################

def space_list(request):
    spaces = Space.objects.all()

    def add_child(space):
        model = PROTOCOL[space.access_protocol]['model']
        child = model.objects.get(space=space)
        space.child = model_to_dict(child,
            PROTOCOL[space.access_protocol]['fields'] or [''])
    map(add_child, spaces)
    return render(request, 'locations/space_list.html', locals())

def space_detail(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    model = PROTOCOL[space.access_protocol]['model']
    child = model.objects.get(space=space)
    space.child = model_to_dict(child,
        PROTOCOL[space.access_protocol]['fields']or [''])
    locations = Location.objects.filter(space=space)
    return render(request, 'locations/space_detail.html', locals())

def space_create(request):
    if request.method == 'POST':
        space_form = SpaceForm(request.POST, prefix='space')
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
                return redirect('space_list')
                # return redirect('space_detail', space.uuid)
        else:
            # We need to return the protocol_form so that protocol_form errors
            # are displayed, and so the form doesn't mysterious disappear
            # See if access_protocol has been set
            access_protocol = space_form['access_protocol'].value()
            if access_protocol:
                protocol_form = PROTOCOL[access_protocol]['form'](
                   request.POST, prefix='protocol')
    else:
        space_form = SpaceForm(prefix='space')

    return render(request, 'locations/space_form.html', locals())

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
