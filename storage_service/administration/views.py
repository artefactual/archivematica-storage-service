import logging
import subprocess

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.urlresolvers import reverse
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import get_language, ugettext as _
from django.template import RequestContext
from tastypie.models import ApiKey

from common import utils
from common import gpgutils
from common import decorators

from storage_service import __version__ as ss_version
from locations.models import GPG
from . import forms as settings_forms


LOGGER = logging.getLogger(__name__)


# ######################## ADMIN ##########################

def settings_edit(request):
    initial_data = utils.get_all_settings()
    common_form = settings_forms.CommonSettingsForm(request.POST or None,
        initial=initial_data, prefix='common')
    default_location_form = settings_forms.DefaultLocationsForm(
        request.POST or None, initial=initial_data, prefix='default_loc')
    if common_form.is_valid() and default_location_form.is_valid():
        # Save settings
        common_form.save()
        default_location_form.save()
        messages.success(request, _("Setting saved."))
        return redirect('settings_edit')
    return render(request, 'administration/settings_form.html', locals())


# ######################## VERSION ########################

def get_git_commit():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'])
    except (OSError, subprocess.CalledProcessError):
        return None


def version_view(request):
    return render(request, 'administration/version.html',
        {'version': ss_version,
         'git_commit': get_git_commit()})


# ######################## USERS ##########################

def user_list(request):
    users = get_user_model().objects.all()
    return render(request, 'administration/user_list.html', locals())


def user_edit(request, id):
    action = _("Edit User")
    edit_user = get_object_or_404(get_user_model(), id=id)
    user_form = settings_forms.UserChangeForm(request.POST or None, instance=edit_user)
    password_form = SetPasswordForm(data=request.POST or None, user=edit_user)
    if 'user' in request.POST and user_form.is_valid():
        user_form.save()
        messages.success(request, _("User information saved."))
        return redirect('user_list')
    elif 'password' in request.POST and password_form.is_valid():
        password_form.save()
        api_key = ApiKey.objects.get(user=edit_user)
        api_key.key = api_key.generate_key()
        api_key.save()
        messages.success(request, _("Password changed."))
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())


def user_create(request):
    action = _("Create User")
    user_form = settings_forms.UserCreationForm(request.POST or None)
    if user_form.is_valid():
        user_form.save()
        messages.success(request, _("New user %(username)s created.") % {'username': user_form.cleaned_data['username']})
        return redirect('user_list')
    return render(request, 'administration/user_form.html', locals())


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
        generic_language = current_language.split('-')[0]
        if generic_language in languages:
            language_selection = generic_language

    return render(request, 'administration/language_form.html', {
        'language_selection': language_selection
    })


########################## KEYS ##########################

def key_list(request):
    """List all of the GPG keys that the SS knows about."""
    keys = gpgutils.get_gpg_key_list()
    return render(request, 'administration/key_list.html', locals())


def key_detail(request, key_fingerprint):
    """View details (including ASCII armor) of GPG key with fingerprint
    ``key_fingerprint``.
    """
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            'GPG key with fingerprint {} does not exist.'.format(
                key_fingerprint))
    public_armor, private_armor = gpgutils.export_gpg_key(key['fingerprint'])
    return render(request, 'administration/key_detail.html', locals())


def key_create(request):
    """Create a new key using the POST params; currently these are just the
    real name and email of the key's user/owner.
    """
    action = "Create"
    key_form = settings_forms.KeyCreateForm(request.POST or None)
    if key_form.is_valid():
        cd = key_form.cleaned_data
        key = gpgutils.generate_gpg_key(cd['name_real'], cd['name_email'])
        if key:
            messages.success(request, "New key {} created.".format(
                key.fingerprint))
            return redirect('key_list')
        else:
            messages.warning(
                request,
                "Failed to create key with real name '{}' and email"
                " '{}'.".format(cd['name_real'], cd['name_email']))
    return render(request, 'administration/key_form.html', locals())


def key_import(request):
    """Import an existing key to the storage service by providing its ASCII
    armor in a form field. To get the ASCII armored private key with
    fingerprint ``fingerprint`` via Python GnuPG::

        >>> gpg.export_keys(fingerprint, True)

    From the shell::

        $ gpg --armor --export-secret-keys $FINGERPRINT

    TODO: we should confirm that all keys that a user attempts to import have
    empty passphrases. Otherwise, packages could get encrypted and SS (with no
    way of prompting for a GPG passphrase at present) would not be able to
    decrypt them. See http://blog.jasonantman.com/2013/08/testing-gpg-key-passphrases/
    """
    action = "Import"
    key_form = settings_forms.KeyImportForm(request.POST or None)
    if key_form.is_valid():
        cd = key_form.cleaned_data
        fingerprint = gpgutils.import_gpg_key(cd['ascii_armor'])
        if fingerprint:
            messages.success(request, "New key {} created.".format(
                fingerprint))
            return redirect('key_list')
        else:
            messages.warning(
                request,
                "Failed to create key with the supplied ASCII armor")
    return render(request, 'administration/key_form.html', locals())


def key_delete_context(request, key_fingerprint):
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            'GPG key with fingerprint {} does not exist.'.format(
                key_fingerprint))
    header = 'Confirm deleting GPG key {} ({})'.format(
        ', '.join(key['uids']), key_fingerprint)
    dependent_gpg_spaces = GPG.objects.filter(key=key_fingerprint)
    if dependent_gpg_spaces:
        prompt = ('GPG key {} cannot be deleted because at least one GPG Space'
                  ' is using it for encryption.'.format(key_fingerprint))
    else:
        prompt = 'Are you sure you want to delete GPG key {}?'.format(
            key_fingerprint)
    default_cancel = reverse('key_list')
    cancel_url = request.GET.get('next', default_cancel)
    context_dict = {
        'header': header,
        'dependent_objects': dependent_gpg_spaces,
        'prompt': prompt,
        'cancel_url': cancel_url,
    }
    return RequestContext(request, context_dict)


@decorators.confirm_required('administration/key_delete.html',
                             key_delete_context)
def key_delete(request, key_fingerprint):
    key = gpgutils.get_gpg_key(key_fingerprint)
    if not key:
        raise Http404(
            'GPG key with fingerprint {} does not exist.'.format(
                key_fingerprint))
    result = gpgutils.delete_gpg_key(key_fingerprint)
    if result is True:
        messages.success(
            request,
            'GPG key {} successfully deleted.'.format(key_fingerprint))
    else:
        messages.warning(
            request,
            'Failed to delete GPG key {}.'.format(key_fingerprint))
    next_url = request.GET.get('next', reverse('key_list'))
    return redirect(next_url)
