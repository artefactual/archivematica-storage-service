
from django.shortcuts import render, redirect

from . import forms
from . import models


########################## ADMIN ##########################

def settings_edit(request):
    initial_data = dict(models.Settings.objects.all().values_list('name', 'value'))
    if request.method == 'POST':
        form = forms.SettingsForm(request.POST, initial=initial_data)
        if form.is_valid():
            # Save settings
            form.save()
            return redirect('settings_edit')
    else:
        form = forms.SettingsForm(initial=initial_data)

    return render(request, 'administration/settings_form.html', locals())
