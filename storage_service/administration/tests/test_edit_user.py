from django.contrib.auth.models import User
from django.test import TestCase


class TestEditUser(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser(
            username='admin', password='admin', email='admin@example.com'
        )
        super(TestEditUser, cls).setUpTestData()

    def setUp(self):
        self.client.login(username='admin', password='admin')
        self.test_user = User.objects.get(username='test')

    def test_get_form(self):
        self.client.get('/administration/users/1/edit/')
        self.assertTemplateUsed('user_form.html')

    def test_change_user_details_only(self):
        old_password = self.test_user.password
        old_api_key = self.test_user.api_key.key
        response = self.client.post(
            '/administration/users/1/edit/',
            {
                'username': 'test',
                'first_name': 'New first name',
                'last_name': 'New last name',
                'email_address': 'test@example.com',
                'new_password1': '',
                'new_password2': '',
            },
            follow=True
        )

        self.test_user.refresh_from_db()
        self.test_user.api_key.refresh_from_db()

        # User fields should be updated
        assert self.test_user.first_name == 'New first name'
        assert self.test_user.last_name == 'New last name'

        # Password and api key should not change
        assert self.test_user.password == old_password
        assert self.test_user.api_key.key == old_api_key

        # Should redirect back to user list
        self.assertRedirects(response, '/administration/users/')

        # Should show a messages saying the user info was saved
        messages = {m.message for m in response.context['messages']}
        assert 'User information saved.' in messages

    def test_with_change_password(self):
        old_password = self.test_user.password
        old_api_key = self.test_user.api_key.key
        response = self.client.post(
            '/administration/users/1/edit/',
            {
                'username': 'test',
                'first_name': 'first name',
                'last_name': 'new last name',
                'email_address': 'test@example.com',
                'new_password1': 'mypassword',
                'new_password2': 'mypassword',
            },
            follow=True
        )

        self.test_user.refresh_from_db()
        self.test_user.api_key.refresh_from_db()

        # User edits should take effect
        assert self.test_user.last_name == 'new last name'

        # Password and api key should both change
        assert self.test_user.password != old_password
        assert self.test_user.api_key.key != old_api_key

        # Should redirect back to user list
        self.assertRedirects(response, '/administration/users/')

        # Should show a message saying the user info was saved
        messages = {m.message for m in response.context['messages']}
        assert 'Password changed.' in messages
        assert 'User information saved.' in messages

    def test_user_edit_form_error(self):
        """
        When there's an error in the edit user form, it should not
        save the password form
        """
        old_password = self.test_user.password
        response = self.client.post(
            '/administration/users/1/edit/',
            {
                'username': '',     # username is missing
                'first_name': 'first name',
                'last_name': 'last name',
                'email_address': 'test@example.com',
                'new_password1': 'mypassword',
                'new_password2': 'mypassword',
            },
        )

        self.test_user.refresh_from_db()

        # Make sure no password change
        assert self.test_user.password == old_password

        # Should display the form page again
        self.assertTemplateUsed('user_form.html')
        assert len(response.context['messages']) == 0

    def test_password_form_error(self):
        """
        When there's an error in the password form, it should not
        save the user edit form
        """
        response = self.client.post(
            '/administration/users/1/edit/',
            {
                'username': 'test',     # username is missing
                'first_name': 'new first name',
                'last_name': 'last name',
                'email_address': 'test@example.com',
                'new_password1': 'mypassword',
                'new_password2': 'mismatch',
            },
        )

        # Make sure no password change
        self.test_user.refresh_from_db()
        assert self.test_user.first_name == ''

        # Should display the form page again
        self.assertTemplateUsed('user_form.html')
        assert len(response.context['messages']) == 0
