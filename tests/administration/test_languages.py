import pytest
import pytest_django
from django.test import Client
from pytest_django.asserts import assertTemplateUsed


@pytest.mark.django_db
def test_displays_language_form(logged_in_client: Client) -> None:
    response = logged_in_client.get("/administration/language/")

    assertTemplateUsed(response, "administration/language_form.html")


@pytest.mark.django_db
def test_selects_correct_language_on_form(
    settings: pytest_django.Settings, logged_in_client: Client
) -> None:
    settings.LANGUAGE_CODE = "es"

    response = logged_in_client.get("/administration/language/")

    assert response.context["language_selection"] == "es"


@pytest.mark.django_db
def test_falls_back_to_generic_language(
    settings: pytest_django.Settings, logged_in_client: Client
) -> None:
    settings.LANGUAGE_CODE = "es-es"

    response = logged_in_client.get("/administration/language/")

    assert response.context["language_selection"] == "es"


@pytest.mark.django_db
def test_switch_language(
    settings: pytest_django.Settings, logged_in_client: Client
) -> None:
    settings.LANGUAGE_CODE = "en-us"

    response = logged_in_client.post(
        "/i18n/setlang/",
        {"language": "fr", "next": "/administration/language/"},
        follow=True,
    )

    assert response.context["language_selection"] == "fr"
