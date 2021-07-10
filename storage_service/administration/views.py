import logging
import subprocess

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.translation import get_language, ugettext as _
from tastypie.models import ApiKey

from common import utils
from common import gpgutils
from common import decorators

from storage_service import __version__ as ss_version
from locations.models import GPG, Package
from . import forms as settings_forms


LOGGER = logging.getLogger(__name__)


# ######################## ADMIN ##########################


def settings_edit(request):
    initial_data = utils.get_all_settings()
    common_form = settings_forms.CommonSettingsForm(
        request.POST or None, initial=initial_data, prefix="common"
    )
    default_location_form = settings_forms.DefaultLocationsForm(
        request.POST or None, initial=initial_data, prefix="default_loc"
    )
    if common_form.is_valid() and default_location_form.is_valid():
        # Save settings
        common_form.save()
        default_location_form.save()
        messages.success(request, _("Setting saved."))
        return redirect("administration:settings_edit")
    return render(request, "administration/settings_form.html", locals())


# ######################## VERSION ########################


def get_git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"])
    except (OSError, subprocess.CalledProcessError):
        return None


def version_view(request):
    return render(
        request,
        "administration/version.html",
        {"version": ss_version, "git_commit": get_git_commit()},
    )


# ######################## USERS ##########################


def user_list(request):
    users = get_user_model().objects.all()
    allow_user_edits = settings.ALLOW_USER_EDITS
    return render(request, "administration/user_list.html", locals())


def user_edit(request, id):
    edit_allowed = settings.ALLOW_USER_EDITS and (
        request.user.is_superuser or str(request.user.id) == id
    )
    if not edit_allowed:
        return redirect("administration:user_list")

    action = _("Edit User")
    edit_user = get_object_or_404(get_user_model(), id=id)
    user_form = settings_forms.UserChangeForm(
        request.POST or None, instance=edit_user, current_user=request.user
    )
    password_form = SetPasswordForm(data=request.POST or None, user=edit_user)
    if "user" in request.POST and user_form.is_valid():
        user_form.save()
        messages.success(request, _("User information saved."))
        return redirect("administration:user_list")
    elif "password" in request.POST and password_form.is_valid():
        password_form.save()
        api_key = ApiKey.objects.get(user=edit_user)
        api_key.key = api_key.generate_key()
        api_key.save()
        messages.success(request, _("Password changed."))
        return redirect("administration:user_list")
    elif "password":
        # Ensure user form information still displays after an invalid
        # password change attempt.
        user_form = settings_forms.UserChangeForm(
            instance=edit_user, current_user=request.user
        )
    return render(request, "administration/user_form.html", locals())


def user_create(request):
    create_allowed = settings.ALLOW_USER_EDITS and request.user.is_superuser
    if not create_allowed:
        return redirect("administration:user_list")

    action = _("Create User")
    user_form = settings_forms.UserCreationForm(request.POST or None)
    if user_form.is_valid():
        user_form.save()
        messages.success(
            request,
            _("New user %(username)s created.")
            % {"username": user_form.cleaned_data["username"]},
        )
        return redirect("administration:user_list")
    return render(request, "administration/user_form.html", locals())


def user_detail(request, id):
    # Only a superuser or the user themselves can view their full details
    view_allowed = request.user.is_superuser or str(request.user.id) == id
    if not view_allowed:
        return redirect("administration:user_list")

    display_user = get_object_or_404(get_user_model(), id=id)

    return render(
        request, "administration/user_detail.html", {"display_user": display_user}
    )


# ######################## LANGUAGE ##########################


def change_language(request):
    current_language = get_language()
    language_selection = None

    # Fall back to a generic language if the selected language
    # is too specific (e.g. en-us can fall back to en)
    languages = dict(settings.LANGUAGES)
    if current_language in languages:
        language_selection = current_language
    else:
        generic_language = current_language.split("-")[0]
        if generic_language in languages:
            language_selection = generic_language

    return render(
        request,
        "administration/language_form.html",
        {"language_selection": language_selection},
    )


# ######################### KEYS ##########################


def key_list(request):
    """List all of the GPG keys that the SS knows about."""
    keys = gpgutils.get_gpg_key_list()
    return render(request, "administration/key_list.html", locals())


def key_detail(request, key_fingerprint):
    """View details (including ASCII armor) of GPG key with fingerprint
    ``key_fingerprint``.
    """
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            _(
                "GPG key with fingerprint %(fingerprint)s does not exist."
                % {"fingerprint": key_fingerprint}
            )
        )
    public_armor, private_armor = gpgutils.export_gpg_key(key["fingerprint"])
    return render(request, "administration/key_detail.html", locals())


def key_create(request):
    """Create a new key using the POST params; currently these are just the
    real name and email of the key's user/owner.
    """
    action_ = "Create Key"
    action = _(action_)
    key_form = settings_forms.KeyCreateForm(request.POST or None)
    if key_form.is_valid():
        cd = key_form.cleaned_data
        key = gpgutils.generate_gpg_key(cd["name_real"], cd["name_email"])
        if key:
            messages.success(
                request,
                _(
                    "New key %(fingerprint)s created."
                    % {"fingerprint": key.fingerprint}
                ),
            )
            LOGGER.debug('created new GPG key for "%s"', cd["name_real"])
            return redirect("administration:key_list")
        else:
            messages.warning(
                request,
                _(
                    "Failed to create key with real name '%(name_real)s' and"
                    " email '%(name_email)s'."
                    % {"name_real": cd["name_real"], "name_email": cd["name_email"]}
                ),
            )
    explanation = _(
        "Generate a new GPG key. The key will not have a passphrase. It will be"
        " a key of type %(key_type)s and length %(key_length)s."
        % {"key_type": gpgutils.DFLT_KEY_TYPE, "key_length": gpgutils.DFLT_KEY_LENGTH}
    )
    return render(
        request,
        "administration/key_form.html",
        {
            "action_": action_,
            "action": action,
            "explanation": explanation,
            "key_form": key_form,
        },
    )


def key_import(request):
    """Import an existing key to the storage service by providing its ASCII
    armor in a form field. To get the ASCII armored private key with
    fingerprint ``fingerprint`` via Python GnuPG::

        >>> gpg.export_keys(fingerprint, True)

    From the shell::

        $ gpg --armor --export-secret-keys $FINGERPRINT

    """
    action_ = "Import Key"
    action = _(action_)
    key_form = settings_forms.KeyImportForm(request.POST or None)
    if key_form.is_valid():
        cd = key_form.cleaned_data
        fingerprint = gpgutils.import_gpg_key(cd["ascii_armor"])
        if fingerprint == gpgutils.IMPORT_ERROR:
            messages.error(
                request,
                _(
                    "Import failed. Sorry, we were unable to create a key with"
                    " the supplied ASCII armor"
                ),
            )
        elif fingerprint == gpgutils.PASSPHRASED:
            messages.error(
                request,
                _(
                    "Import failed. The GPG key provided requires a passphrase."
                    " GPG keys with passphrases cannot be imported"
                ),
            )
        else:
            messages.success(
                request,
                _(f"New key {fingerprint} created."),
            )
            return redirect("administration:key_list")
    explanation = _(
        "Import an existing GPG key. Paste here the ASCII armor of the GPG"
        " private key, which you can get by running <code>gpg --armor"
        " --export-secret-keys</code> followed by the fingerprint, email or name"
        " associated with the key. The key should begin with <code>-----BEGIN"
        " PGP PRIVATE KEY BLOCK-----</code> and end with <code>-----END PGP"
        " PRIVATE KEY BLOCK-----</code> and it must not have a passphrase."
    )
    return render(
        request,
        "administration/key_form.html",
        {
            "action_": action_,
            "action": action,
            "explanation": explanation,
            "key_form": key_form,
        },
    )


def key_delete_context(request, key_fingerprint):
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            _(
                "GPG key with fingerprint %(fingerprint)s does not exist."
                % {"fingerprint": key_fingerprint}
            )
        )
    header = _(
        "Confirm deleting GPG key %(uids)s (%(fingerprint)s)"
        % {"uids": ", ".join(key["uids"]), "fingerprint": key_fingerprint}
    )
    prompt = ""
    dependent_objects = GPG.objects.filter(key=key_fingerprint)
    if dependent_objects:
        messages.error(
            request,
            _(
                "GPG key %(fingerprint)s cannot be deleted because at least"
                " one GPG Space is using it for encryption."
                % {"fingerprint": key_fingerprint}
            ),
        )
    else:
        LOGGER.debug("No dependent GPG spaces")
        dependent_objects = Package.objects.filter(
            encryption_key_fingerprint=key_fingerprint
        ).exclude(status=Package.DELETED)
        if dependent_objects:
            LOGGER.debug("HAVE dependent packages")
            messages.error(
                request,
                _(
                    "GPG key %(fingerprint)s cannot be deleted because at least"
                    " one package (AIP, transfer) needs it in order to be"
                    " decrypted." % {"fingerprint": key_fingerprint}
                ),
            )
        else:
            LOGGER.debug("No dependent packages")
            prompt = _(
                "Are you sure you want to delete GPG key"
                " %(fingerprint)s?" % {"fingerprint": key_fingerprint}
            )
    default_cancel = reverse("administration:key_list")
    cancel_url = request.GET.get("next", default_cancel)
    return {
        "header": header,
        "dependent_objects": dependent_objects,
        "prompt": prompt,
        "cancel_url": cancel_url,
    }


@decorators.confirm_required("administration/key_delete.html", key_delete_context)
def key_delete(request, key_fingerprint):
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            _(
                "GPG key with fingerprint %(fingerprint)s does not exist."
                % {"fingerprint": key_fingerprint}
            )
        )
    result = gpgutils.delete_gpg_key(key_fingerprint)
    if result is True:
        messages.success(
            request,
            _(
                "GPG key %(fingerprint)s successfully deleted."
                % {"fingerprint": key_fingerprint}
            ),
        )
    else:
        messages.warning(
            request,
            _(
                "Failed to delete GPG key %(fingerprint)s."
                % {"fingerprint": key_fingerprint}
            ),
        )
    next_url = request.GET.get("next", reverse("administration:key_list"))
    return redirect(next_url)
