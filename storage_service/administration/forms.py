from django import forms
from django.contrib import auth
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from common import utils

from locations.models import Location, Space


# ######################## CUSTOM FIELDS/WIDGETS ##########################


class DefaultLocationWidget(forms.MultiWidget):
    """ Widget for entering required information to create a new location. """

    template_name = "administration/location_widget.html"

    def __init__(self, *args, **kwargs):
        widgets = [
            forms.Select(choices=[], *args, **kwargs),  # space_id
            forms.TextInput(*args, **kwargs),  # relative_path
            forms.TextInput(*args, **kwargs),  # description
            forms.TextInput(*args, **kwargs),  # quota
        ]
        super().__init__(widgets=widgets, *args, **kwargs)

    def set_space_id_choices(self, choices):
        self.widgets[0].choices += choices

    def decompress(self, value):
        """ Splits initial data to a list for each sub-widget. """
        try:
            return [
                value["space_id"],
                value["relative_path"],
                value["description"],
                value["quota"],
            ]
        except (KeyError, TypeError):
            return []

    def get_context(self, *args, **kwargs):
        labels = (_("Space"), _("Relative Path"), _("Description"), _("Quota"))
        result = super().get_context(*args, **kwargs)
        result["labeled_widgets"] = zip(labels, result["widget"]["subwidgets"])
        return result


class DefaultLocationField(forms.MultiValueField):
    """ Field for entering required information to create a new location. """

    def __init__(self, *args, **kwargs):
        space_id = forms.ChoiceField(choices=[], *args, **kwargs)
        relative_path = forms.CharField(*args, **kwargs)
        description = forms.CharField(*args, **kwargs)
        quota = forms.IntegerField(min_value=0, *args, **kwargs)
        fields = [space_id, relative_path, description, quota]
        widget = DefaultLocationWidget()
        super().__init__(fields=fields, widget=widget, *args, **kwargs)

    def set_space_id_choices(self, choices):
        self.fields[0].choices += choices
        self.widget.set_space_id_choices(choices)

    def compress(self, data_list):
        """ Takes widget data and compresses to one data structure. """
        if data_list and len(data_list) == 4:
            return {
                "space_id": data_list[0],
                "relative_path": data_list[1].rstrip("/") + "/",
                "description": data_list[2],
                "quota": data_list[3],
            }
        return {}


# ######################## SETTINGS ##########################


class SettingsForm(forms.Form):
    """ For all forms that save data to Settings model. """

    def save(self, *args, **kwargs):
        """ Save each of the fields in the form to the Settings table. """
        for setting, value in self.cleaned_data.items():
            utils.set_setting(setting, value)


class CommonSettingsForm(SettingsForm):
    """ Configures common or generic settings that don't belong elsewhere. """

    pipelines_disabled = forms.BooleanField(
        required=False, label=_("Pipelines are disabled upon creation?")
    )
    object_counting_disabled = forms.BooleanField(
        required=False, label=_("Object counting in spaces is disabled?")
    )
    recover_request_notification_url = forms.URLField(
        required=False, label=_("Recovery request: URL to notify")
    )
    recover_request_notification_auth_username = forms.CharField(
        required=False, label=_("Recovery request notification: Username (optional)")
    )
    recover_request_notification_auth_password = forms.CharField(
        required=False, label=_("Recovery request notification: Password (optional)")
    )


class DefaultLocationsForm(SettingsForm):
    """ Configures default locations associated with a new pipeline. """

    # This allows to look for the custom template of the DefaultLocationWidget
    # in the DIRS paths of the default templates backend (see settings.TEMPLATES)
    default_renderer = forms.renderers.TemplatesSetting

    default_transfer_source = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label=_("Default transfer source locations for new pipelines:"),
    )
    new_transfer_source = DefaultLocationField(
        required=False, label=_("New Transfer Source:")
    )
    default_aip_storage = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label=_("Default AIP storage locations for new pipelines"),
    )
    new_aip_storage = DefaultLocationField(required=False, label=_("New AIP Storage:"))
    default_dip_storage = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label=_("Default DIP storage locations for new pipelines"),
    )
    new_dip_storage = DefaultLocationField(required=False, label=_("New DIP Storage:"))
    default_backlog = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label=_("Default transfer backlog locations for new pipelines:"),
    )
    new_backlog = DefaultLocationField(required=False, label=_("New Transfer Backlog:"))
    default_recovery = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label=_("Default AIP recovery locations for new pipelines:"),
    )
    new_recovery = DefaultLocationField(required=False, label=_("New AIP Recovery:"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamic choices done in init, because did not update consistently in
        # field definition
        self.fields["default_transfer_source"].choices = [
            (loc.uuid, loc.get_description())
            for loc in Location.active.filter(purpose=Location.TRANSFER_SOURCE)
        ] + [("new", _("Create new location for each pipeline"))]
        self.fields["default_aip_storage"].choices = [
            (loc.uuid, loc.get_description())
            for loc in Location.active.filter(purpose=Location.AIP_STORAGE)
        ] + [("new", _("Create new location for each pipeline"))]
        self.fields["default_dip_storage"].choices = [
            (loc.uuid, loc.get_description())
            for loc in Location.active.filter(purpose=Location.DIP_STORAGE)
        ] + [("new", _("Create new location for each pipeline"))]
        self.fields["default_backlog"].choices = [
            (loc.uuid, loc.get_description())
            for loc in Location.active.filter(purpose=Location.BACKLOG)
        ] + [("new", _("Create new location for each pipeline"))]
        self.fields["default_recovery"].choices = [
            (loc.uuid, loc.get_description())
            for loc in Location.active.filter(purpose=Location.AIP_RECOVERY)
        ] + [("new", _("Create new location for each pipeline"))]
        space_id_choices = [(s.uuid, str(s)) for s in Space.objects.all()]
        for field_name in self.fields:
            field = self.fields[field_name]
            if isinstance(field, DefaultLocationField):
                field.set_space_id_choices(space_id_choices)

    def clean(self):
        cleaned_data = super().clean()
        # Check that if a field has 'new' it filled in the new location info
        if "new" in cleaned_data["default_transfer_source"]:
            location_data = cleaned_data.get("new_transfer_source")
            if location_data and not location_data["relative_path"]:
                raise forms.ValidationError(_("Relative path is required"))
            if location_data and location_data["relative_path"][0] == "/":
                raise forms.ValidationError(_("Relative path cannot start with /"))
        if "new" in cleaned_data["default_aip_storage"]:
            location_data = cleaned_data.get("new_aip_storage")
            if location_data and not location_data["relative_path"]:
                raise forms.ValidationError(_("Relative path is required"))
            if location_data and location_data["relative_path"][0] == "/":
                raise forms.ValidationError(_("Relative path cannot start with /"))
        if "new" in cleaned_data["default_recovery"]:
            location_data = cleaned_data.get("new_aip_recovery")
            if location_data and not location_data["relative_path"]:
                raise forms.ValidationError(_("Relative path is required"))
            if location_data and location_data["relative_path"][0] == "/":
                raise forms.ValidationError(_("Relative path cannot start with /"))
        return cleaned_data

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # do something with create_new if it exists


# ######################## USERS ##########################


class UserCreationForm(auth.forms.UserCreationForm):
    """Creates a new user. Inherits from Django's UserCreationForm."""

    email = forms.EmailField(required=True, help_text=_("Required."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_superuser"].label = _("Administrator?")
        self.fields["is_superuser"].initial = True

    class Meta:
        model = auth.get_user_model()
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
            "is_superuser",
        )

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 != "" and password2 != "":
            if password1 != password2:
                raise ValidationError(
                    self.error_messages["password_mismatch"], code="password_mismatch"
                )
        return password2

    def _post_clean(self):
        super()._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
        password = self.cleaned_data.get("password1")
        if password:
            try:
                validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password1", error)


class UserChangeForm(auth.forms.UserChangeForm):
    """Modifies an existing user. Inherits from Django's UserChangeForm."""

    def __init__(self, *args, **kwargs):
        current_user = kwargs.pop("current_user", None)
        self.user_being_edited = kwargs["instance"]
        self.superusers = auth.get_user_model().objects.filter(is_superuser=True)
        super().__init__(*args, **kwargs)
        self.fields["is_superuser"].label = _("Administrator?")
        if not (current_user and current_user.is_superuser):
            # If current user is not super, do not permit editing of that.
            del self.fields["is_superuser"]
        elif self.superusers.count() == 1 and current_user == self.user_being_edited:
            # Provide some indication that this is undesirable.
            self.fields["is_superuser"].widget.attrs["readonly"] = True
        del self.fields["password"]

    def clean(self):
        """Validate the form to protect against potential user errors."""
        if self.superusers.count() > 1:
            return self.cleaned_data
        try:
            # Protect field from being reverted if only one superuser.
            if self.user_being_edited.is_superuser:
                self.cleaned_data["is_superuser"] = True
        except KeyError:
            # Field isn't being modified, nothing to do.
            pass
        return self.cleaned_data

    class Meta:
        model = auth.get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_superuser")


# ######################### KEYS ##########################


class KeyCreateForm(forms.Form):
    required_css_class = "required-field"
    name_real = forms.CharField(label=_("Name"))
    name_email = forms.EmailField(label=_("Email"), required=False)


class KeyImportForm(forms.Form):
    ascii_armor = forms.CharField(widget=forms.Textarea)
