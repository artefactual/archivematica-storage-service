from django.contrib.auth.models import User
from django.test import TestCase
from django.test import override_settings


class TestLanguageSwitching(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        User.objects.create_user(
            username="admin", password="admin", email="admin@example.com"
        )

    def setUp(self):
        self.client.login(username="admin", password="admin")

    def test_displays_language_form(self):
        self.client.get("/administration/language/")
        self.assertTemplateUsed("language_form.html")

    @override_settings(LANGUAGE_CODE="es")
    def test_selects_correct_language_on_form(self):
        response = self.client.get("/administration/language/")
        assert response.context["language_selection"] == "es"

    @override_settings(LANGUAGE_CODE="es-es")
    def test_falls_back_to_generic_language(self):
        response = self.client.get("/administration/language/")
        assert response.context["language_selection"] == "es"

    @override_settings(LANGUAGE_CODE="en-us")
    def test_switch_language(self):
        response = self.client.post(
            "/i18n/setlang/",
            {"language": "fr", "next": "/administration/language/"},
            follow=True,
        )
        assert response.context["language_selection"] == "fr"
