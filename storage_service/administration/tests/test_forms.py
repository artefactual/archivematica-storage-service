from django.contrib.auth.models import User
from django.test import TestCase


class TestSetPasswordForm(TestCase):
    def setUp(self):
        self.test_user = User.objects.get(username='test')

    def create_form(self, data):
        # This has to be done here because of attempted database accesses on
        # import (DefaultLocationsForm)
        from administration.forms import SetPasswordForm
        return SetPasswordForm(data=data, user=self.test_user)

    def test_is_empty_if_neither_field_filled_in(self):
        form = self.create_form({
            'new_password1': '',
            'new_password2': '',
        })
        assert form.is_empty()

    def test_is_non_empty_if_one_field_filled_in(self):
        form = self.create_form({
            'new_password1': 'something',
            'new_password2': '',
        })

        assert not form.is_empty()
