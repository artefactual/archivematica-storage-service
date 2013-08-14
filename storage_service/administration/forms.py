
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from common import utils


class SettingsForm(forms.Form):
    pipelines_disabled = forms.BooleanField(required=False,
        label="Pipelines are disabled upon creation?")

    def __init__(self, *args, **kwargs):
        # Convert all "False" strings to boolean False
        if 'initial' in kwargs:
            for k in kwargs['initial']:
                if kwargs['initial'][k] == "False":
                    kwargs['initial'][k] = False
        super(SettingsForm, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        """ Save each of the fields in the form to the Settings table. """
        for key in self.cleaned_data:
            utils.set_setting(key, self.cleaned_data[key])


########################## USERS ##########################

class UserCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super(UserCreationForm, self).__init__(*args, **kwargs)
        self.fields['is_superuser'].label = "Administrator?"
        self.fields['is_superuser'].initial = True

    class Meta:
        model = get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'is_superuser')


class UserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super(UserChangeForm, self).__init__(*args, **kwargs)
        self.fields['is_superuser'].label = "Administrator?"
        del self.fields['password']

    class Meta:
        model = get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email', 'is_superuser')
