
from django import forms

from . import models

class PipelineForm(forms.ModelForm):
    create_default_locations = forms.BooleanField(required=False,
        initial=True,
        label="Default Locations:",
        help_text="Enabled if default locations should be created for this pipeline")

    class Meta:
        model = models.Pipeline
        fields = ('uuid', 'description', 'enabled')


class SpaceForm(forms.ModelForm):
    class Meta:
        model = models.Space
        fields = ('access_protocol', 'size', 'path', 'staging_path')

    def __init__(self, *args, **kwargs):
        super(SpaceForm, self).__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.uuid:
            # If editing (not creating a new object) access protocol shouldn't
            # be changed.  Remove from fields, print in template
            del self.fields['access_protocol']

    def clean_access_protocol(self):
        instance = getattr(self, 'instance', None)
        if instance and instance.uuid:
            return instance.access_protocol
        else:
            return self.cleaned_data['access_protocol']

class LocalFilesystemForm(forms.ModelForm):
    class Meta:
        model = models.LocalFilesystem
        fields = ()


class NFSForm(forms.ModelForm):
    class Meta:
        model = models.NFS
        fields = ('remote_name', 'remote_path', 'version', 'manually_mounted')


class PipelineLocalFSForm(forms.ModelForm):
    # TODO SpaceForm.path help text should say path to space on local machine
    class Meta:
        model = models.PipelineLocalFS
        fields = ('remote_user', 'remote_name', )


class LocationForm(forms.ModelForm):
    class Meta:
        model = models.Location
        fields = ('purpose', 'pipeline', 'relative_path', 'description', 'quota', 'enabled')


class ConfirmEventForm(forms.ModelForm):
    class Meta:
        model = models.Event
        fields = ('status_reason',)

    def __init__(self, *args, **kwargs):
        super(ConfirmEventForm, self).__init__(*args, **kwargs)
        self.fields['status_reason'].required = True
