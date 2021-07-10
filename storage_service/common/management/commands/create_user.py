from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tastypie.models import ApiKey


class Command(BaseCommand):
    help = (
        "Create user with all the arguments specified. "
        "If the user already exists its attributes will be updated."
    )
    args = ("username", "email", "password", "api_key", "superuser")

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--api-key", required=True)
        parser.add_argument("--superuser", action="store_true", default=False)

    def handle(self, *args, **options):
        UserModel = get_user_model()
        user = None
        try:
            user = UserModel._default_manager.get(
                **{UserModel.USERNAME_FIELD: options["username"]}
            )
            print("User found.")
        except UserModel.DoesNotExist:
            if options["superuser"]:
                user = UserModel._default_manager.create_superuser(
                    options["username"], options["email"], options["password"]
                )
            else:
                user = UserModel._default_manager.create_user(
                    options["username"], options["email"], options["password"]
                )
            print("User could not be found, one was created.")

        if user is None:
            raise CommandError("User not found!")

        user.email = options["email"]
        user.set_password(options["password"])
        user.save()
        print("User updated.")

        obj, created = ApiKey.objects.update_or_create(
            user=user, defaults={"key": options["api_key"]}
        )
        print("API key created.") if created else print("API key updated.")
