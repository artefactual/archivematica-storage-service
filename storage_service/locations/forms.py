from __future__ import absolute_import
import logging

from django import forms
import django.utils
import django.core.exceptions
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from common import gpgutils
from locations import models


LOGGER = logging.getLogger(__name__)


# CUSTOM WIDGETS
# Move this to a widgets.py file if there are more than a couple


class DisableableSelectWidget(forms.Select):
    """
    Modification of Select widget to allow specific choices to be disabled.

    Set disabled_choices to the values of the choices that should be disabled.
    Custom clean methods should also be added to ensure those values cannot be
    chosen.

    Example:
    def __init__(self, *args, **kwargs):
        super(ThisForm, self).__init__(*args, **kwargs)
        self.fields['choicesfield'].widget.disabled_choices = (value1, value2)
    """

    # From https://djangosnippets.org/snippets/2743/
    # Updated for Django 1.5 Select widget
    def __init__(self, attrs=None, disabled_choices=(), choices=()):
        super(DisableableSelectWidget, self).__init__(attrs, choices)
        self.disabled_choices = list(disabled_choices)

    def render_option(self, selected_choices, option_value, option_label):
        option_value = django.utils.encoding.force_text(option_value)
        if option_value in selected_choices:
            selected_html = mark_safe(' selected="selected"')
            if not self.allow_multiple_selected:
                # Only allow for a single selection.
                selected_choices.remove(option_value)
        else:
            selected_html = ""
        if option_value in self.disabled_choices:
            disabled_html = mark_safe(' disabled="disabled"')
        else:
            disabled_html = ""
        return django.utils.html.format_html(
            '<option value="{0}"{1}{2}>{3}</option>',
            option_value,
            selected_html,
            disabled_html,
            django.utils.encoding.force_text(option_label),
        )


# FORMS


class PipelineForm(forms.ModelForm):
    create_default_locations = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Default Locations:"),
        help_text=_("Enabled if default locations should be created for this pipeline"),
    )

    class Meta:
        model = models.Pipeline
        fields = (
            "uuid",
            "description",
            "remote_name",
            "api_username",
            "api_key",
            "enabled",
        )


class SpaceForm(forms.ModelForm):
    class Meta:
        model = models.Space
        fields = ("access_protocol", "size", "path", "staging_path")

    def __init__(self, *args, **kwargs):
        super(SpaceForm, self).__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        self.filter_beta_protocols()
        if instance and instance.uuid:
            # If editing (not creating a new object) access protocol shouldn't
            # be changed.  Remove from fields, print in template
            del self.fields["access_protocol"]

    def filter_beta_protocols(self):
        """Remove the Space.BETA_PROTOCOLS from the "Access protocol:" field's
        choices.
        """
        filtered_protocols = [
            choice
            for choice in list(self.fields["access_protocol"].choices)
            if choice[0] not in self._meta.model.BETA_PROTOCOLS
        ]
        self.fields["access_protocol"].choices = filtered_protocols
        self.fields["access_protocol"].widget.choices = filtered_protocols

    def clean_access_protocol(self):
        instance = getattr(self, "instance", None)
        if instance and instance.uuid:
            return instance.access_protocol
        else:
            return self.cleaned_data["access_protocol"]


class ArkivumForm(forms.ModelForm):
    class Meta:
        model = models.Arkivum
        fields = ("host", "remote_user", "remote_name")


class DataverseForm(forms.ModelForm):
    class Meta:
        model = models.Dataverse
        fields = ("host", "api_key", "agent_name", "agent_type", "agent_identifier")

    def as_p(self):
        # Add a warning to the Dataverse-specific section of the form
        content = super(DataverseForm, self).as_p()
        content += '\n<div class="alert">{}</div>'.format(
            _("Integration with Dataverse is currently a beta feature")
        )
        return mark_safe(content)


class DuracloudForm(forms.ModelForm):
    class Meta:
        model = models.Duracloud
        fields = ("host", "user", "password", "duraspace")


class DSpaceForm(forms.ModelForm):
    class Meta:
        model = models.DSpace
        fields = ("sd_iri", "user", "password", "metadata_policy", "archive_format")


class DSpaceRESTForm(forms.ModelForm):
    class Meta:
        model = models.DSpaceREST
        fields = (
            "ds_rest_url",
            "ds_user",
            "ds_password",
            "ds_dip_collection",
            "ds_aip_collection",
            "as_url",
            "as_user",
            "as_password",
            "as_repository",
            "as_archival_object",
            "upload_to_tsm",
            "verify_ssl",
        )

    def as_p(self):
        """Override in order to add an alert in the ArchivesSpace subsection
        of the form.
        """
        content = super(DSpaceRESTForm, self).as_p()
        needle = '<p><label for="id_protocol-as_url">'
        as_fields_alert = '<div class="alert">{}</div>\n{}'.format(
            _(
                "The ArchivesSpace fields are optional. Leaving any of these"
                " fields blank will prevent ArchivesSpace linking requests from"
                " being sent, unless the metadata is included in the packages"
                " METS file in a dmdSec."
            ),
            needle,
        )
        return django.utils.safestring.mark_safe(
            content.replace(needle, as_fields_alert)
        )


def get_gpg_key_choices():
    return [
        (key["fingerprint"], ", ".join(key["uids"]))
        for key in gpgutils.get_gpg_key_list()
    ]


class GPGForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(GPGForm, self).__init__(*args, **kwargs)
        system_key = gpgutils.get_default_gpg_key(gpgutils.get_gpg_key_list())
        self.fields["key"] = forms.ChoiceField(
            choices=get_gpg_key_choices(), initial=system_key["fingerprint"]
        )

    class Meta:
        model = models.GPG
        fields = ("key",)


class LocalFilesystemForm(forms.ModelForm):
    class Meta:
        model = models.LocalFilesystem
        fields = ()


class NFSForm(forms.ModelForm):
    class Meta:
        model = models.NFS
        fields = ("remote_name", "remote_path", "version", "manually_mounted")


class PipelineLocalFSForm(forms.ModelForm):
    # TODO SpaceForm.path help text should say path to space on local machine
    class Meta:
        model = models.PipelineLocalFS
        fields = ("remote_user", "remote_name", "assume_rsync_daemon", "rsync_password")


class LockssomaticForm(forms.ModelForm):
    # TODO SpaceForm.path help text should say path to staging space, preferably local
    class Meta:
        model = models.Lockssomatic
        fields = ("sd_iri", "content_provider_id", "external_domain", "keep_local")

    def clean_external_domain(self):
        data = self.cleaned_data["external_domain"]
        data = data.rstrip("/")
        return data


class FedoraForm(forms.ModelForm):
    class Meta:
        model = models.Fedora
        fields = ("fedora_user", "fedora_password", "fedora_name")


class SwiftForm(forms.ModelForm):
    class Meta:
        model = models.Swift
        fields = (
            "auth_url",
            "auth_version",
            "username",
            "password",
            "container",
            "tenant",
            "region",
        )


class S3Form(forms.ModelForm):
    class Meta:
        model = models.S3
        fields = ("endpoint_url", "access_key_id", "secret_access_key", "region")


class LocationForm(forms.ModelForm):
    default = forms.BooleanField(
        required=False, label=_("Set as global default location for its purpose")
    )

    class Meta:
        model = models.Location
        fields = (
            "purpose",
            "pipeline",
            "relative_path",
            "description",
            "quota",
            "enabled",
            "default",
            "replicators",
        )

        widgets = {"purpose": DisableableSelectWidget()}

    def __init__(self, *args, **kwargs):
        """
        Should be passed parameter 'space_protocol' which is the entry from
        Space.ACCESS_PROTOCOL_CHOICES that this Location belongs to.
        """
        space_protocol = kwargs.get("space_protocol")
        del kwargs["space_protocol"]
        super(LocationForm, self).__init__(*args, **kwargs)
        # Disable purposes that aren't in the Space's whitelist
        all_ = set(x[0] for x in models.Location.PURPOSE_CHOICES)
        if space_protocol in [x[0] for x in models.Space.ACCESS_PROTOCOL_CHOICES]:
            from .constants import PROTOCOL

            self.whitelist = PROTOCOL[space_protocol]["model"].ALLOWED_LOCATION_PURPOSE
        else:
            self.whitelist = all_
        blacklist = all_ - set(self.whitelist)
        self.fields["purpose"].widget.disabled_choices = blacklist
        # A possible replicator for a Location is any RP-purposed location
        # other than the current one.
        replicator_choices = models.Location.objects.filter(
            enabled=True, purpose=models.Location.REPLICATOR
        ).all()
        instance_uuid = getattr(kwargs.get("instance"), "uuid", None)
        self.fields["replicators"].widget.choices = [
            (repl_loc.id, str(repl_loc))
            for repl_loc in replicator_choices
            if repl_loc.uuid != instance_uuid
        ]
        # Associated with all enabled pipelines by default
        self.fields["pipeline"].initial = models.Pipeline.active.values_list(
            "pk", flat=True
        )
        self.fields["default"].initial = self.instance.default
        # If we are accessing a Dataverse we want to be able to do nice things
        # with the Transfer Browser. Create a namespace to work with the path
        # here.
        if space_protocol == models.Space.DATAVERSE:
            dv_config = "Query: \nSubtree: "
            self.fields["relative_path"].initial = dv_config
            # Help text for the relative path field on the Dataverse form. The
            # form itself is not very responsive, so the smallest amount of
            # text has been used to try and convey something useful.
            dv_help_text = _(
                "Path to location, relative to the storage space's path. "
                "Optional. Filter Dataverse by matches and/or Dataverse "
                "subtree."
            )
            self.fields["relative_path"].help_text = dv_help_text

    def clean(self):
        cleaned_data = super(LocationForm, self).clean()
        purpose = cleaned_data.get("purpose")

        # Only AIP Storage AS-purposed locations can have replicators
        replicators = cleaned_data.get("replicators")
        if purpose != models.Location.AIP_STORAGE and replicators:
            raise forms.ValidationError(
                _("Only AIP storage locations can have replicators")
            )

        if purpose == models.Location.AIP_RECOVERY:
            # Don't allow more than one recovery location per pipeline
            # Fetch all LocationPipelines linked to an AIP Recovery location and
            # one of the Pipeline's we're adding
            # Exclude this Location, since we already know it's associated
            # Group by pipeline and count the number of Locations
            # Any Location indicates a duplicate
            existing_recovery_rel = (
                models.LocationPipeline.objects.filter(
                    location__purpose=models.Location.AIP_RECOVERY,
                    pipeline__in=list(cleaned_data.get("pipeline", [])),
                )
                .exclude(location_id=self.instance.uuid)
                .values(
                    # Group by pipeline
                    "pipeline"
                )
                .annotate(
                    # Count associated locations
                    total=Count("location")
                )
            )
            pipelines = [d["pipeline"] for d in existing_recovery_rel]
            if pipelines:
                raise forms.ValidationError(
                    _(
                        "Pipeline(s) %(pipelines)s already have an AIP recovery location."
                    )
                    % {"pipelines": ", ".join(pipelines)}
                )
        return cleaned_data

    def clean_purpose(self):
        # Server-side enforcement of what Location purposes are allowed
        data = self.cleaned_data["purpose"]
        if data not in self.whitelist:
            raise django.core.exceptions.ValidationError(_("Invalid purpose"))
        return data

    def save(self, commit=True):
        self.instance.default = self.cleaned_data["default"]
        return super(LocationForm, self).save(commit=commit)


class ConfirmEventForm(forms.ModelForm):
    class Meta:
        model = models.Event
        fields = ("status_reason",)

    def __init__(self, *args, **kwargs):
        super(ConfirmEventForm, self).__init__(*args, **kwargs)
        self.fields["status_reason"].required = True


class CallbackForm(forms.ModelForm):
    class Meta:
        model = models.Callback
        fields = ("uri", "event", "method", "expected_status")


class ReingestForm(forms.Form):
    REINGEST_CHOICES = (
        (models.Package.METADATA_ONLY, _("Metadata re-ingest")),
        (models.Package.OBJECTS, _("Partial re-ingest")),
        (models.Package.FULL, _("Full re-ingest")),
    )

    pipeline = forms.ModelChoiceField(
        label=_("Pipeline"), queryset=models.Pipeline.active.all()
    )
    reingest_type = forms.ChoiceField(
        label=_("Reingest type"), choices=REINGEST_CHOICES, widget=forms.RadioSelect
    )
    processing_config = forms.CharField(
        required=False,
        initial="default",
        label=_("Processing config"),
        help_text=_("Optional: The processing config is only used with full re-ingest"),
        widget=forms.TextInput(attrs={"placeholder": "default"}),
    )
