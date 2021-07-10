from django.db import models, migrations
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [("locations", "0002_v0_4")]

    operations = [
        migrations.CreateModel(
            name="Callback",
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
                        max_length=36, editable=False, blank=True
                    ),
                ),
                (
                    "uri",
                    models.CharField(
                        help_text=b"URL to contact upon callback execution.",
                        max_length=1024,
                    ),
                ),
                (
                    "event",
                    models.CharField(
                        help_text=b"Type of event when this callback should be executed.",
                        max_length=15,
                        choices=[(b"post_store", b"Post-store")],
                    ),
                ),
                (
                    "method",
                    models.CharField(
                        help_text=b"HTTP request method to use in connecting to the URL.",
                        max_length=10,
                        choices=[
                            (b"delete", b"DELETE"),
                            (b"get", b"GET"),
                            (b"head", b"HEAD"),
                            (b"options", b"OPTIONS"),
                            (b"patch", b"PATCH"),
                            (b"post", b"POST"),
                            (b"put", b"PUT"),
                        ],
                    ),
                ),
                (
                    "expected_status",
                    models.IntegerField(
                        default=200,
                        help_text=b"Expected HTTP response from the server, used to validate the callback response.",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text=b"Enabled if this callback should be executed.",
                    ),
                ),
            ],
            options={"verbose_name": "Callback"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Duracloud",
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
                    "host",
                    models.CharField(
                        help_text=b"Hostname of the DuraCloud instance. Eg. trial.duracloud.org",
                        max_length=256,
                    ),
                ),
                (
                    "user",
                    models.CharField(
                        help_text=b"Username to authenticate as", max_length=64
                    ),
                ),
                (
                    "password",
                    models.CharField(
                        help_text=b"Password to authenticate with", max_length=64
                    ),
                ),
                (
                    "duraspace",
                    models.CharField(
                        help_text=b"Name of the Space within DuraCloud", max_length=64
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "DuraCloud"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Fedora",
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
                    "fedora_user",
                    models.CharField(
                        help_text=b"Fedora user name (for SWORD functionality)",
                        max_length=64,
                    ),
                ),
                (
                    "fedora_password",
                    models.CharField(
                        help_text=b"Fedora password (for SWORD functionality)",
                        max_length=256,
                    ),
                ),
                (
                    "fedora_name",
                    models.CharField(
                        help_text=b"Name or IP of the remote Fedora machine.",
                        max_length=256,
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "FEDORA"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="File",
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
                ("name", models.TextField(max_length=1000)),
                ("source_id", models.TextField(max_length=128)),
                ("checksum", models.TextField(max_length=128)),
                ("stored", models.BooleanField(default=False)),
            ],
            options={"verbose_name": "Callback File"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="PackageDownloadTask",
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
                ("downloads_attempted", models.IntegerField(default=0)),
                ("downloads_completed", models.IntegerField(default=0)),
                (
                    "download_completion_time",
                    models.DateTimeField(default=None, null=True, blank=True),
                ),
                (
                    "package",
                    models.ForeignKey(
                        to="locations.Package",
                        to_field="uuid",
                        on_delete=models.CASCADE,
                    ),
                ),
            ],
            options={"verbose_name": "Package Download Task"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="PackageDownloadTaskFile",
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
                ("filename", models.CharField(max_length=256)),
                ("url", models.TextField()),
                (
                    "completed",
                    models.BooleanField(
                        default=False,
                        help_text=b"True if file downloaded successfully.",
                    ),
                ),
                (
                    "failed",
                    models.BooleanField(
                        default=False, help_text=b"True if file failed to download."
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        related_name="download_file_set",
                        to="locations.PackageDownloadTask",
                        to_field="uuid",
                        on_delete=models.CASCADE,
                    ),
                ),
            ],
            options={"verbose_name": "Package Download Task File"},
            bases=(models.Model,),
        ),
        migrations.AlterModelOptions(
            name="lockssomatic", options={"verbose_name": "LOCKSS-o-matic"}
        ),
        migrations.AddField(
            model_name="package",
            name="description",
            field=models.CharField(
                default=None,
                max_length=256,
                null=True,
                help_text=b"Human-readable description.",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="pipeline",
            name="api_key",
            field=models.CharField(
                default=None,
                max_length=256,
                null=True,
                help_text=b"API key to use when making API calls to the pipeline.",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="pipeline",
            name="api_username",
            field=models.CharField(
                default=None,
                max_length=256,
                null=True,
                help_text=b"Username to use when making API calls to the pipeline.",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="pipeline",
            name="remote_name",
            field=models.CharField(
                default=None,
                max_length=256,
                null=True,
                help_text=b"Host or IP address of the pipeline server for making API calls.",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="location",
            name="purpose",
            field=models.CharField(
                help_text=b"Purpose of the space.  Eg. AIP storage, Transfer source",
                max_length=2,
                choices=[
                    (b"AS", b"AIP Storage"),
                    (b"CP", b"Currently Processing"),
                    (b"DS", b"DIP Storage"),
                    (b"SD", b"FEDORA Deposits"),
                    (b"SS", b"Storage Service Internal Processing"),
                    (b"BL", b"Transfer Backlog"),
                    (b"TS", b"Transfer Source"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="package",
            name="origin_pipeline",
            field=models.ForeignKey(
                to_field="uuid",
                blank=True,
                to="locations.Pipeline",
                null=True,
                on_delete=models.CASCADE,
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="package",
            name="package_type",
            field=models.CharField(
                max_length=8,
                choices=[
                    (b"AIP", b"AIP"),
                    (b"AIC", b"AIC"),
                    (b"SIP", b"SIP"),
                    (b"DIP", b"DIP"),
                    (b"transfer", b"Transfer"),
                    (b"file", b"Single File"),
                    (b"deposit", b"FEDORA Deposit"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="package",
            name="status",
            field=models.CharField(
                default=b"FAIL",
                help_text=b"Status of the package in the storage service.",
                max_length=8,
                choices=[
                    (b"PENDING", b"Upload Pending"),
                    (b"STAGING", b"Staged on Storage Service"),
                    (b"UPLOADED", b"Uploaded"),
                    (b"VERIFIED", b"Verified"),
                    (b"FAIL", b"Failed"),
                    (b"DEL_REQ", b"Delete requested"),
                    (b"DELETED", b"Deleted"),
                    (b"FINALIZE", b"Deposit Finalized"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text=b"How the space can be accessed.",
                max_length=8,
                choices=[
                    (b"DC", b"DuraCloud"),
                    (b"FEDORA", b"FEDORA via SWORD2"),
                    (b"FS", b"Local Filesystem"),
                    (b"LOM", b"LOCKSS-o-matic"),
                    (b"NFS", b"NFS"),
                    (b"PIPE_FS", b"Pipeline Local Filesystem"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="space",
            name="path",
            field=models.TextField(
                default=b"",
                help_text=b"Absolute path to the space on the storage service machine.",
                blank=True,
            ),
            preserve_default=True,
        ),
    ]
