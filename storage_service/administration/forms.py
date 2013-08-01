
from django import forms

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
