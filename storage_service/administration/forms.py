
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from common import utils

from locations.models import Location


########################## SETTINGS ##########################

class SettingsForm(forms.Form):
    """ For all forms that save data to Settings model. """

    def save(self, *args, **kwargs):
        """ Save each of the fields in the form to the Settings table. """
        for setting, value in self.cleaned_data.iteritems():
            utils.set_setting(setting, value)


class CommonSettingsForm(SettingsForm):
    pipelines_disabled = forms.BooleanField(required=False,
        label="Pipelines are disabled upon creation?")


class DefaultLocationsForm(SettingsForm):
    default_transfer_source = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default transfer source locations for new pipelines:")
    default_aip_storage = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default AIP storage locations for new pipelines")

    def __init__(self, *args, **kwargs):
        super(DefaultLocationsForm, self).__init__(*args, **kwargs)
        # Dynamic choices done in init, because did not update consistently in
        # field definition
        self.fields['default_transfer_source'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.TRANSFER_SOURCE)]
        self.fields['default_aip_storage'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.AIP_STORAGE)]


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
