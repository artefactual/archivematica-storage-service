from django.conf import settings


def auth_methods(request):
    return {"oidc_enabled": settings.OIDC_AUTHENTICATION}
