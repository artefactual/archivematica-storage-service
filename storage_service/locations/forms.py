
from django.forms import ModelForm

from .models import Space, LocalFilesystem, NFS, Location, Event, Pipeline


class PipelineForm(ModelForm):
    class Meta:
        model = Pipeline
        fields = ('uuid', 'description', 'enabled')


class SpaceForm(ModelForm):
    class Meta:
        model = Space
        fields = ('access_protocol', 'size', 'path')


class LocalFilesystemForm(ModelForm):
    class Meta:
        model = LocalFilesystem
        fields = ()


class NFSForm(ModelForm):
    class Meta:
        model = NFS
        fields = ('remote_name', 'remote_path', 'version', 'manually_mounted')


class LocationForm(ModelForm):
    class Meta:
        model = Location
        fields = ('purpose', 'pipeline', 'relative_path', 'description', 'quota', 'enabled')


class ConfirmEventForm(ModelForm):
    class Meta:
        model = Event
        fields = ('status_reason',)

    def __init__(self, *args, **kwargs):
        super(ConfirmEventForm, self).__init__(*args, **kwargs)
        self.fields['status_reason'].required = True
