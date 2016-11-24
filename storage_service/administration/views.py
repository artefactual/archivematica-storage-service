import subprocess

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import render, redirect, get_object_or_404
from tastypie.models import ApiKey

from common import utils
from storage_service import __version__ as ss_version
from . import forms as settings_forms


########################## ADMIN ##########################

def settings_edit(request):
    initial_data = utils.get_all_settings()
    common_form = settings_forms.CommonSettingsForm(request.POST or None,
        initial=initial_data, prefix='common')
    default_location_form = settings_forms.DefaultLocationsForm(
        request.POST or None, initial=initial_data, prefix='default_loc')
    if common_form.is_valid() and default_location_form.is_valid():
        # Save settings
        common_form.save()
        default_location_form.save()
        messages.success(request, "Setting saved.")
        return redirect('settings_edit')
    return render(request, 'administration/settings_form.html', locals())


########################## VERSION ########################

def get_git_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'])
    except subprocess.CalledProcessError:
        return None

def version_view(request):
    return render(request, 'administration/version.html',
        {'version': ss_version,
         'git_commit': get_git_commit()})


########################## USERS ##########################

def user_list(request):
    users = get_user_model().objects.all()
    return render(request, 'administration/user_list.html', locals())

def user_edit(request, id):
    action = "Edit"
    edit_user = get_object_or_404(get_user_model(), id=id)
    user_form = settings_forms.UserChangeForm(request.POST or None, instance=edit_user)
    password_form = SetPasswordForm(data=request.POST or None, user=edit_user)
    if 'user' in request.POST and user_form.is_valid():
        user_form.save()
        messages.success(request, "User information saved.")
        return redirect('user_list')
    elif 'password' in request.POST and password_form.is_valid():
        password_form.save()
        api_key = ApiKey.objects.get(user=edit_user)
        api_key.key = api_key.generate_key()
        api_key.save()
        messages.success(request, "Password changed.")
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())

def user_create(request):
    action = "Create"
    user_form = settings_forms.UserCreationForm(request.POST or None)
    if user_form.is_valid():
        user_form.save()
        messages.success(request, "New user {} created.".format(
            user_form.cleaned_data['username']))
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())
