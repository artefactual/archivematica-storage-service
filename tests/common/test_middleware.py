import pytest
import pytest_django
from django.contrib.auth.models import User
from django.test import Client

AUDIT_LOG_MIDDLEWARE = (
    "archivematica.storage_service.common.middleware.AuditLogMiddleware"
)


@pytest.mark.django_db
def test_audit_log_middleware_adds_username(
    settings: pytest_django.Settings, logged_in_client: Client, user: User
) -> None:
    """Test that X-Username is added for authenticated users."""
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, AUDIT_LOG_MIDDLEWARE]

    response = logged_in_client.get("/")

    assert response.has_header("X-Username")
    assert response["X-Username"] == user.username


@pytest.mark.django_db
def test_audit_log_middleware_unauthenticated(
    settings: pytest_django.Settings, logged_in_client: Client
) -> None:
    """Test absence of X-Username header for unauthenticated users.

    First we logout the authenticated user, and then we check for
    the presence of X-Username in the response for a new request by
    an unauthenticated user.
    """
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, AUDIT_LOG_MIDDLEWARE]
    logged_in_client.logout()

    response = logged_in_client.get(settings.LOGIN_URL)

    assert not response.has_header("X-Username")
