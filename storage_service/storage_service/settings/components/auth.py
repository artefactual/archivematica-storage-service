"""Settings for basic user authentication."""

from os import environ

from storage_service.settings.helpers import is_true

PASSWORD_MINIMUM_LENGTH = 8
try:
    PASSWORD_MINIMUM_LENGTH = int(
        environ.get("SS_AUTH_PASSWORD_MINIMUM_LENGTH", PASSWORD_MINIMUM_LENGTH)
    )
except ValueError:
    pass

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": PASSWORD_MINIMUM_LENGTH},
    }
]

# Additional password validation is enabled by default. To disable, set the
# following AUTH_PASSWORD_* settings to false in the environment.
if not is_true(environ.get("SS_AUTH_PASSWORD_DISABLE_COMMON_VALIDATION", "false")):
    AUTH_PASSWORD_VALIDATORS.append(
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}
    )

if not is_true(
    environ.get(
        "SS_AUTH_PASSWORD_DISABLE_USER_ATTRIBUTE_SIMILARITY_VALIDATION", "false"
    )
):
    AUTH_PASSWORD_VALIDATORS.append(
        {
            "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        }
    )

if not is_true(environ.get("SS_AUTH_PASSWORD_DISABLE_COMPLEXITY_VALIDATION", "false")):
    AUTH_PASSWORD_VALIDATORS.append(
        {"NAME": "administration.validators.PasswordComplexityValidator"}
    )
