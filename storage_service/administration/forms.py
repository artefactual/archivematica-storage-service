
from django import forms
from django.contrib import auth

from common import utils

from locations.models import Location, Space


########################## CUSTOM FIELDS/WIDGETS ##########################

class DefaultLocationWidget(forms.MultiWidget):
    """ Widget for entering required information to create a new location. """
    def __init__(self, *args, **kwargs):
        choices = [(s.uuid, str(s)) for s in Space.objects.all()]
        widgets = [
            forms.Select(choices=choices, *args, **kwargs),  # space_id
            forms.TextInput(*args, **kwargs),  # relative_path
            forms.TextInput(*args, **kwargs),  # description
            forms.TextInput(*args, **kwargs),  # quota
        ]
        super(DefaultLocationWidget, self).__init__(widgets=widgets, *args, **kwargs)

    def decompress(self, value):
        """ Splits initial data to a list for each sub-widget. """
        try:
            return [
                value['space_id'],
                value['relative_path'],
                value['description'],
                value['quota']
            ]
        except (KeyError, TypeError):
            return []

    def format_output(self, rendered_widgets):
        html = "<p>Space: {}</p><p>Relative Path: {}</p><p>Description: {}</p><p>Quota: {}</p>".format(
            *rendered_widgets)
        return html


class DefaultLocationField(forms.MultiValueField):
    """ Field for entering required information to create a new location. """
    def __init__(self, *args, **kwargs):
        choices = [(s.uuid, str(s)) for s in Space.objects.all()]
        space_id = forms.ChoiceField(choices=choices, *args, **kwargs)
        relative_path = forms.CharField(*args, **kwargs)
        description = forms.CharField(*args, **kwargs)
        quota = forms.IntegerField(min_value=0, *args, **kwargs)
        fields = [space_id, relative_path, description, quota]
        widget = DefaultLocationWidget()
        super(DefaultLocationField, self).__init__(fields=fields, widget=widget, *args, **kwargs)

    def compress(self, data_list):
        """ Takes widget data and compresses to one data structure. """
        if data_list and len(data_list) == 4:
            return {
                'space_id': data_list[0],
                'relative_path': data_list[1].rstrip('/')+'/',
                'description': data_list[2],
                'quota': data_list[3]
            }
        return {}


########################## SETTINGS ##########################

class SettingsForm(forms.Form):
    """ For all forms that save data to Settings model. """

    def save(self, *args, **kwargs):
        """ Save each of the fields in the form to the Settings table. """
        for setting, value in self.cleaned_data.iteritems():
            utils.set_setting(setting, value)


class CommonSettingsForm(SettingsForm):
    """ Configures common or generic settings that don't belong elsewhere. """
    pipelines_disabled = forms.BooleanField(required=False,
        label="Pipelines are disabled upon creation?")
    recover_request_notification_url = forms.CharField()
    recover_request_notification_auth_username = forms.CharField()
    recover_request_notification_auth_password = forms.CharField()


class DefaultLocationsForm(SettingsForm):
    """ Configures default locations associated with a new pipeline. """
    default_transfer_source = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default transfer source locations for new pipelines:")
    new_transfer_source = DefaultLocationField(
        required=False,
        label="New Transfer Source:")
    default_aip_storage = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default AIP storage locations for new pipelines")
    new_aip_storage = DefaultLocationField(
        required=False,
        label="New AIP Storage:")
    default_dip_storage = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default DIP storage locations for new pipelines")
    new_dip_storage = DefaultLocationField(
        required=False,
        label="New DIP Storage:")
    default_backlog = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default transfer backlog locations for new pipelines:"
        )
    new_backlog = DefaultLocationField(
        required=False,
        label="New Transfer Backlog:")
    default_recovery = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Default AIP recovery locations for new pipelines:"
        )
    new_recovery = DefaultLocationField(
        required=False,
        label="New AIP Recovery:")

    def __init__(self, *args, **kwargs):
        super(DefaultLocationsForm, self).__init__(*args, **kwargs)
        # Dynamic choices done in init, because did not update consistently in
        # field definition
        self.fields['default_transfer_source'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.TRANSFER_SOURCE)] + \
            [('new', 'Create new location for each pipeline')]
        self.fields['default_aip_storage'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.AIP_STORAGE)] + \
            [('new', 'Create new location for each pipeline')]
        self.fields['default_dip_storage'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.DIP_STORAGE)] + \
            [('new', 'Create new location for each pipeline')]
        self.fields['default_backlog'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.BACKLOG)] + \
            [('new', 'Create new location for each pipeline')]
        self.fields['default_recovery'].choices = [
            (l.uuid, l.get_description()) for l in
            Location.active.filter(purpose=Location.AIP_RECOVERY)] + \
            [('new', 'Create new location for each pipeline')]


    def clean(self):
        cleaned_data = super(DefaultLocationsForm, self).clean()
        # Check that if a field has 'new' it filled in the new location info
        if 'new' in cleaned_data['default_transfer_source']:
            location_data = cleaned_data.get('new_transfer_source')
            if location_data and not location_data['relative_path']:
                raise forms.ValidationError("Relative path is required")
            if location_data and location_data['relative_path'][0] == '/':
                raise forms.ValidationError("Relative path cannot start with /")
        if 'new' in cleaned_data['default_aip_storage']:
            location_data = cleaned_data.get('new_aip_storage')
            if location_data and not location_data['relative_path']:
                raise forms.ValidationError("Relative path is required")
            if location_data and location_data['relative_path'][0] == '/':
                raise forms.ValidationError("Relative path cannot start with /")
        if 'new' in cleaned_data['default_recovery']:
            location_data = cleaned_data.get('new_aip_recovery')
            if location_data and not location_data['relative_path']:
                raise forms.ValidationError("Relative path is required")
            if location_data and location_data['relative_path'][0] == '/':
                raise forms.ValidationError("Relative path cannot start with /")
        return cleaned_data

    def save(self, *args, **kwargs):
        super(DefaultLocationsForm, self).save(*args, **kwargs)
        # do something with create_new if it exists


########################## USERS ##########################

class UserCreationForm(auth.forms.UserCreationForm):
    """ Creates a new user.  Inherits from django's UserCreationForm. """
    def __init__(self, *args, **kwargs):
        super(UserCreationForm, self).__init__(*args, **kwargs)
        self.fields['is_superuser'].label = "Administrator?"
        self.fields['is_superuser'].initial = True

    class Meta:
        model = auth.get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'is_superuser')


class UserChangeForm(auth.forms.UserChangeForm):
    """ Modifys an existing user.  Inherits from django's UserChangeForm. """
    def __init__(self, *args, **kwargs):
        super(UserChangeForm, self).__init__(*args, **kwargs)
        self.fields['is_superuser'].label = "Administrator?"
        del self.fields['password']

    class Meta:
        model = auth.get_user_model()
        fields = ('username', 'first_name', 'last_name', 'email', 'is_superuser')
