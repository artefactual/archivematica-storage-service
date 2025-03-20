"""Configure user groups and permissions.

This migration creates two user groups: managers and reviewers. Managers carry
all permissions - they can perform all actions, but they won't be able to
perform user management since it requires the superuser flag. Reviewers are
like regular authenticated users, i.e. they can read and list records, with an
extra `locations.approve_package_deletion` permission that allows them to
accept/reject package deletion requests.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations


def migrate_permissions(apps, schema_editor):
    """Ask Django to persist the permissions before we use them."""
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None


def get_manager_permissions(apps):
    """Return all permissions that belong to the manager role."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    models = [
        apps.get_model("administration", "Settings"),
        apps.get_model("locations", "Arkivum"),
        apps.get_model("locations", "Async"),
        apps.get_model("locations", "Callback"),
        apps.get_model("locations", "Dataverse"),
        apps.get_model("locations", "DSpace"),
        apps.get_model("locations", "DSpaceREST"),
        apps.get_model("locations", "Duracloud"),
        apps.get_model("locations", "Event"),
        apps.get_model("locations", "Fedora"),
        apps.get_model("locations", "File"),
        apps.get_model("locations", "FixityLog"),
        apps.get_model("locations", "GPG"),
        apps.get_model("locations", "LocalFilesystem"),
        apps.get_model("locations", "Location"),
        apps.get_model("locations", "LocationPipeline"),
        apps.get_model("locations", "Lockssomatic"),
        apps.get_model("locations", "NFS"),
        apps.get_model("locations", "OfflineReplicaStaging"),
        apps.get_model("locations", "Package"),
        apps.get_model("locations", "PackageDownloadTask"),
        apps.get_model("locations", "PackageDownloadTaskFile"),
        apps.get_model("locations", "Pipeline"),
        apps.get_model("locations", "PipelineLocalFS"),
        apps.get_model("locations", "S3"),
        apps.get_model("locations", "Space"),
        apps.get_model("locations", "Swift"),
    ]

    # We can't use get_for_models(*models).
    content_types = [ContentType.objects.get_for_model(model) for model in models]

    return Permission.objects.filter(content_type__in=content_types)


def get_reviewer_permissions(apps):
    """Return the ``Package.approve_package_deletion`` permission."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Package = apps.get_model("locations", "Package")
    Permission = apps.get_model("auth", "Permission")

    return Permission.objects.filter(
        content_type=ContentType.objects.get_for_model(Package),
        codename="approve_package_deletion",
    )


def apply_migration(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")

    # Create "Managers" group and attach permissions.
    managers = Group.objects.create(name="Managers")
    managers.permissions.set(get_manager_permissions(apps))

    # Create "Reviewers" group and attach permissions.
    reviewers = Group.objects.create(name="Reviewers")
    reviewers.permissions.set(get_reviewer_permissions(apps))
    reviewers.save()

    # Add existing non-admin users to the "Managers" group.
    users = User.objects.filter(is_superuser=False)
    managers.user_set.add(*users)


def revert_migration(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0029_python3"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="package",
            options={
                "permissions": [
                    (
                        "approve_package_deletion",
                        "Can approve Package deletion requests",
                    )
                ],
                "verbose_name": "Package",
            },
        ),
        migrations.RunPython(migrate_permissions, migrations.RunPython.noop),
        migrations.RunPython(apply_migration, revert_migration),
    ]
