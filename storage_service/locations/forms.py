
from django import forms

from .models import Space, LocalFilesystem, NFS, Location, Event, Pipeline, PipelineLocalFS, SwordServer


class PipelineForm(forms.ModelForm):
    create_default_locations = forms.BooleanField(required=False,
        initial=True,
        label="Default Locations:",
        help_text="Enabled if default locations should be created for this pipeline")

    class Meta:
        model = Pipeline
        fields = ('uuid', 'description', 'remote_name', 'api_username', 'api_key', 'enabled')

class SpaceForm(forms.ModelForm):
    # certain fields should not be editable
    def __init__(self, *args, **kwargs):
        super(SpaceForm, self).__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            self.fields['access_protocol'].widget.attrs['readonly'] = True
            #self.fields['access_protocol'].widget.attrs['disabled'] = True

    def clean_access_protocol(self):
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            return instance.access_protocol
        else:
            return self.cleaned_data['access_protocol']

    class Meta:
        model = Space
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


class SwordServerForm(forms.ModelForm):
    class Meta:
        model = SwordServer
        fields = ('pipeline',)


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
