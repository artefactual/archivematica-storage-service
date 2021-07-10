from django.db import models, migrations
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [("locations", "0003_v0_5")]

    operations = [
        migrations.CreateModel(
            name="Arkivum",
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
                        help_text=b"Hostname of the Arkivum web instance. Eg. arkivum.example.com:8443",
                        max_length=256,
                    ),
                ),
                (
                    "remote_user",
                    models.CharField(
                        help_text=b"Optional: Username on the remote machine accessible via passwordless ssh.",
                        max_length=64,
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "remote_name",
                    models.CharField(
                        help_text=b"Optional: Name or IP of the remote machine.",
                        max_length=256,
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "Arkivum"},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Swift",
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
                    "auth_url",
                    models.CharField(
                        help_text=b"URL to authenticate against", max_length=256
                    ),
                ),
                (
                    "auth_version",
                    models.CharField(
                        default=b"2", help_text=b"OpenStack auth version", max_length=8
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        help_text=b"Username to authenticate as. E.g. http://example.com:5000/v2.0/",
                        max_length=64,
                    ),
                ),
                (
                    "password",
                    models.CharField(
                        help_text=b"Password to authenticate with", max_length=256
                    ),
                ),
                ("container", models.CharField(max_length=64)),
                (
                    "tenant",
                    models.CharField(
                        help_text=b"The tenant/account name, required when connecting to an auth 2.0 system.",
                        max_length=64,
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "region",
                    models.CharField(
                        help_text=b"Optional: Region in Swift",
                        max_length=64,
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "Swift"},
            bases=(models.Model,),
        ),
        migrations.AlterModelOptions(name="file", options={"verbose_name": "File"}),
        migrations.AddField(
            model_name="file",
            name="accessionid",
            field=models.TextField(
                help_text=b"Accession ID of originating transfer", blank=True
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="file",
            name="origin",
            field=django_extensions.db.fields.UUIDField(
                default="",
                help_text=b"Unique identifier of originating Archivematica dashboard",
                max_length=36,
                editable=False,
                blank=True,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="file",
            name="package",
            field=models.ForeignKey(
                to="locations.Package", null=True, on_delete=models.CASCADE
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="file",
            name="source_package",
            field=models.TextField(
                help_text=b"Unique identifier of originating unit", blank=True
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="event",
            name="event_type",
            field=models.CharField(
                max_length=8, choices=[(b"DELETE", b"delete"), (b"RECOVER", b"recover")]
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
                    (b"AR", b"AIP Recovery"),
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
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text=b"How the space can be accessed.",
                max_length=8,
                choices=[
                    (b"ARKIVUM", b"Arkivum"),
                    (b"DC", b"DuraCloud"),
                    (b"FEDORA", b"FEDORA via SWORD2"),
                    (b"FS", b"Local Filesystem"),
                    (b"LOM", b"LOCKSS-o-matic"),
                    (b"NFS", b"NFS"),
                    (b"PIPE_FS", b"Pipeline Local Filesystem"),
                    (b"SWIFT", b"Swift"),
                ],
            ),
            preserve_default=True,
        ),
    ]
