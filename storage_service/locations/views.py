
from django.http import HttpResponse
from django.forms.models import model_to_dict
from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.views.decorators.csrf import csrf_exempt

from common.constants import protocol
from .models import Space, Location
from .forms import SpaceForm, LocationForm

########################## SPACES ##########################

def space_list(request):
    spaces = get_list_or_404(Space)
    def add_child(s):
        model = protocol[s.access_protocol]['model']
        child = model.objects.get(space=s)
        s.child = model_to_dict(child, protocol[s.access_protocol]['fields']or [''])
    map(add_child, spaces)
    return render(request, 'locations/space_list.html', locals())

def space_detail(request, uuid):
    space = get_object_or_404(Space, uuid=uuid)
    model = protocol[space.access_protocol]['model']
    child = model.objects.get(space=space)
    space.child = model_to_dict(child, protocol[space.access_protocol]['fields']or [''])
    locations = Location.objects.filter(storage_space=space)
    return render(request, 'locations/space_detail.html', locals())

def space_create(request):
    if request.method == 'POST':
        space_form = SpaceForm(request.POST, prefix='space')
        if space_form.is_valid():
            # Get access protocol form to validate
            access_protocol = space_form.cleaned_data['access_protocol']
            protocol_form = protocol[access_protocol]['form'](
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
                protocol_form = protocol[access_protocol]['form'](
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
            form_class = protocol[sent_protocol]['form']
        except KeyError as e:
            response_data = {}
        else:
            # Create and return the form
            form = form_class(prefix='protocol')
            response_data = form.as_p()
    return HttpResponse(response_data, content_type="text/html")

########################## LOCATIONS ##########################

def location_create(request, space_uuid):
    space = get_object_or_404(Space, uuid=space_uuid)
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save(commit=False)
            location.storage_space = space
            location.save()
            return redirect('space_detail', space.uuid)
    else:
        form = LocationForm()
    return render(request, 'locations/location_form.html', locals())

def location_list(request):
    locations = Location.enabled.all()
    # TODO sort by purpose?  Or should that be done in the template?
    return render(request, 'locations/location_list.html', locals())


