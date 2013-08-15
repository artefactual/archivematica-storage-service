
from django import forms

from .models import Space, LocalFilesystem, NFS, Location, Event, Pipeline, PipelineLocalFS


class PipelineForm(forms.ModelForm):
    create_default_locations = forms.BooleanField(required=False,
        initial=True,
        label="Default Locations:",
        help_text="Enabled if default locations should be created for this pipeline")

    class Meta:
        model = Pipeline
        fields = ('uuid', 'description', 'enabled')


class SpaceForm(forms.ModelForm):
    class Meta:
        model = Space
        fields = ('access_protocol', 'size', 'path')


class LocalFilesystemForm(forms.ModelForm):
    class Meta:
        model = LocalFilesystem
        fields = ()


class NFSForm(forms.ModelForm):
    class Meta:
        model = NFS
        fields = ('remote_name', 'remote_path', 'version', 'manually_mounted')


class PipelineLocalFSForm(forms.ModelForm):
    # TODO SpaceForm.path help text should say path to space on local machine
    class Meta:
        model = PipelineLocalFS
        fields = ('remote_user', 'remote_name', )


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ('purpose', 'pipeline', 'relative_path', 'description', 'quota', 'enabled')


class ConfirmEventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ('status_reason',)

    def __init__(self, *args, **kwargs):
        super(ConfirmEventForm, self).__init__(*args, **kwargs)
        self.fields['status_reason'].required = True
