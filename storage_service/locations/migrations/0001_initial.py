from django.db import models, migrations
import locations.models
from django.conf import settings
import django.core.validators
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "event_type",
                    models.CharField(max_length=8, choices=[(b"DELETE", b"delete")]),
                ),
                ("event_reason", models.TextField()),
                ("user_id", models.PositiveIntegerField()),
                ("user_email", models.EmailField(max_length=254)),
                (
                    "status",
                    models.CharField(
                        max_length=8,
                        choices=[
                            (b"SUBMIT", b"Submitted"),
                            (b"APPROVE", b"Approved"),
                            (b"REJECT", b"Rejected"),
                        ],
                    ),
                ),
                ("status_reason", models.TextField(null=True, blank=True)),
                ("status_time", models.DateTimeField(auto_now=True)),
                ("store_data", models.TextField(null=True, editable=False, blank=True)),
                (
                    "admin_id",
                    models.ForeignKey(
                        blank=True,
                        to=settings.AUTH_USER_MODEL,
                        null=True,
                        on_delete=models.CASCADE,
                    ),
                ),
            ],
            options={"verbose_name": "Event"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="LocalFilesystem",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                )
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Location",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "uuid",
                    django_extensions.db.fields.UUIDField(
                        help_text=b"Unique identifier",
                        unique=True,
                        max_length=36,
                        editable=False,
                        blank=True,
                    ),
                ),
                (
                    "purpose",
                    models.CharField(
                        help_text=b"Purpose of the space.  Eg. AIP storage, Transfer source",
                        max_length=2,
                        choices=[
                            (b"TS", b"Transfer Source"),
                            (b"AS", b"AIP Storage"),
                            (b"CP", b"Currently Processing"),
                        ],
                    ),
                ),
                (
                    "relative_path",
                    models.TextField(
                        help_text=b"Path to location, relative to the storage space's path."
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        default=None,
                        max_length=256,
                        null=True,
                        help_text=b"Human-readable description.",
                        blank=True,
                    ),
                ),
                (
                    "quota",
                    models.BigIntegerField(
                        default=None,
                        help_text=b"Size, in bytes (optional)",
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "used",
                    models.BigIntegerField(
                        default=0, help_text=b"Amount used, in bytes."
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True, help_text=b"True if space can be accessed."
                    ),
                ),
            ],
            options={"verbose_name": "Location"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="LocationPipeline",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        to="locations.Location",
                        to_field="uuid",
                        on_delete=models.CASCADE,
                    ),
                ),
            ],
            options={"verbose_name": "Location associated with a Pipeline"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="NFS",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "remote_name",
                    models.CharField(
                        help_text=b"Name of the NFS server.", max_length=256
                    ),
                ),
                (
                    "remote_path",
                    models.TextField(
                        help_text=b"Path on the NFS server to the export."
                    ),
                ),
                (
                    "version",
                    models.CharField(
                        default=b"nfs4",
                        help_text=b"Type of the filesystem, i.e. nfs, or nfs4.         Should match a command in `mount`.",
                        max_length=64,
                    ),
                ),
                ("manually_mounted", models.BooleanField(default=False)),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Package",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "uuid",
                    django_extensions.db.fields.UUIDField(
                        help_text=b"Unique identifier",
                        unique=True,
                        max_length=36,
                        editable=False,
                        blank=True,
                    ),
                ),
                ("current_path", models.TextField()),
                ("pointer_file_path", models.TextField(null=True, blank=True)),
                ("size", models.IntegerField(default=0)),
                (
                    "package_type",
                    models.CharField(
                        max_length=8,
                        choices=[
                            (b"AIP", b"AIP"),
                            (b"AIC", b"AIC"),
                            (b"SIP", b"SIP"),
                            (b"DIP", b"DIP"),
                            (b"transfer", b"Transfer"),
                            (b"file", b"Single File"),
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        default=b"FAIL",
                        help_text=b"Status of the package in the storage service.",
                        max_length=8,
                        choices=[
                            (b"PENDING", b"Upload Pending"),
                            (b"UPLOADED", b"Uploaded"),
                            (b"VERIFIED", b"Verified"),
                            (b"FAIL", b"Failed"),
                            (b"DEL_REQ", b"Delete requested"),
                            (b"DELETED", b"Deleted"),
                        ],
                    ),
                ),
                (
                    "current_location",
                    models.ForeignKey(
                        to="locations.Location",
                        to_field="uuid",
                        on_delete=models.CASCADE,
                    ),
                ),
            ],
            options={"verbose_name": "Package"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Pipeline",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "uuid",
                    django_extensions.db.fields.UUIDField(
                        validators=[
                            django.core.validators.RegexValidator(
                                b"\\w{8}-\\w{4}-\\w{4}-\\w{4}-\\w{12}",
                                b"Needs to be format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx where x is a hexadecimal digit.",
                                b"Invalid UUID",
                            )
                        ],
                        editable=False,
                        max_length=36,
                        blank=True,
                        help_text=b"Identifier for the Archivematica pipeline",
                        unique=True,
                        verbose_name="UUID",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        default=None,
                        max_length=256,
                        null=True,
                        help_text=b"Human readable description of the Archivematica instance.",
                        blank=True,
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text=b"Enabled if this pipeline is able to access the storage service.",
                    ),
                ),
            ],
            options={"verbose_name": "Pipeline"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="PipelineLocalFS",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "remote_user",
                    models.CharField(
                        help_text=b"Username on the remote machine accessible via ssh",
                        max_length=64,
                    ),
                ),
                (
                    "remote_name",
                    models.CharField(
                        help_text=b"Name or IP of the remote machine.", max_length=256
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Space",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "uuid",
                    django_extensions.db.fields.UUIDField(
                        help_text=b"Unique identifier",
                        unique=True,
                        max_length=36,
                        editable=False,
                        blank=True,
                    ),
                ),
                (
                    "access_protocol",
                    models.CharField(
                        help_text=b"How the space can be accessed.",
                        max_length=8,
                        choices=[
                            (b"FS", b"Local Filesystem"),
                            (b"NFS", b"NFS"),
                            (b"PIPE_FS", b"Pipeline Local Filesystem"),
                        ],
                    ),
                ),
                (
                    "size",
                    models.BigIntegerField(
                        default=None,
                        help_text=b"Size in bytes (optional)",
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "used",
                    models.BigIntegerField(
                        default=0, help_text=b"Amount used in bytes"
                    ),
                ),
                (
                    "path",
                    models.TextField(
                        help_text=b"Absolute path to the space on the storage service machine.",
                        validators=[locations.models.space.validate_space_path],
                    ),
                ),
                (
                    "verified",
                    models.BooleanField(
                        default=False,
                        help_text=b"Whether or not the space has been verified to be accessible.",
                    ),
                ),
                (
                    "last_verified",
                    models.DateTimeField(
                        default=None,
                        help_text=b"Time this location was last verified to be accessible.",
                        null=True,
                        blank=True,
                    ),
                ),
            ],
            options={"verbose_name": "Space"},
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name="pipelinelocalfs",
            name="space",
            field=models.OneToOneField(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="package",
            name="origin_pipeline",
            field=models.ForeignKey(
                to="locations.Pipeline", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="package",
            name="pointer_file_location",
            field=models.ForeignKey(
                related_name="+",
                to_field="uuid",
                blank=True,
                to="locations.Location",
                null=True,
                on_delete=models.CASCADE,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="nfs",
            name="space",
            field=models.OneToOneField(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="locationpipeline",
            name="pipeline",
            field=models.ForeignKey(
                to="locations.Pipeline", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="location",
            name="pipeline",
            field=models.ManyToManyField(
                help_text=b"UUID of the Archivematica instance using this location.",
                to="locations.Pipeline",
                null=True,
                through="locations.LocationPipeline",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="location",
            name="space",
            field=models.ForeignKey(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="localfilesystem",
            name="space",
            field=models.OneToOneField(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="event",
            name="package",
            field=models.ForeignKey(
                to="locations.Package", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="event",
            name="pipeline",
            field=models.ForeignKey(
                to="locations.Pipeline", to_field="uuid", on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
    ]
