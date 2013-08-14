
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.shortcuts import render, redirect, get_object_or_404

from . import forms as settings_forms
from . import models


########################## ADMIN ##########################

def settings_edit(request):
    initial_data = dict(models.Settings.objects.all().values_list('name', 'value'))
    form = settings_forms.SettingsForm(request.POST or None, initial=initial_data)
    if form.is_valid():
        # Save settings
        form.save()
        return redirect('settings_edit')
    return render(request, 'administration/settings_form.html', locals())


########################## USERS ##########################

def user_list(request):
    users = get_user_model().objects.all()
    return render(request, 'administration/user_list.html', locals())

def user_edit(request, username):
    action = "Edit"
    edit_user = get_object_or_404(get_user_model(), username=username)
    user_form = settings_forms.UserChangeForm(request.POST or None, instance=edit_user)
    password_form = SetPasswordForm(data=request.POST or None, user=edit_user)
    if 'user' in request.POST and user_form.is_valid():
        user_form.save()
        return redirect('user_list')
    elif 'password' in request.POST and password_form.is_valid():
        password_form.save()
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())

def user_create(request):
    action = "Create"
    user_form = settings_forms.UserCreationForm(request.POST or None)
    if user_form.is_valid():
        user_form.save()
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())
