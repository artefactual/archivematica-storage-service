# -*- coding: utf-8 -*-

"""Migration to add a Tape Archive Space to the Storage Service."""

from __future__ import absolute_import, unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Entry point for Tape Archive Space migration."""

    dependencies = [("locations", "0026_update_package_status")]
    operations = [
        migrations.CreateModel(
            name="TAR",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tape Archive (TAR) on Local Filesystem",
            },
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                choices=[
                    (b"ARKIVUM", "Arkivum"),
                    (b"DV", "Dataverse"),
                    (b"DC", "DuraCloud"),
                    (b"DSPACE", "DSpace via SWORD2 API"),
                    (b"DSPC_RST", "DSpace via REST API"),
                    (b"FEDORA", "FEDORA via SWORD2"),
                    (b"GPG", "GPG encryption on Local Filesystem"),
                    (b"FS", "Local Filesystem"),
                    (b"LOM", "LOCKSS-o-matic"),
                    (b"NFS", "NFS"),
                    (b"PIPE_FS", "Pipeline Local Filesystem"),
                    (b"SWIFT", "Swift"),
                    (b"S3", "S3"),
                    (b"TAR", "Tape Archive (TAR) on Local Filesystem"),
                ],
                help_text="How the space can be accessed.",
                max_length=8,
                verbose_name="Access protocol",
            ),
        ),
        migrations.AddField(
            model_name="tar",
            name="space",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                to="locations.Space",
                to_field=b"uuid",
            ),
        ),
    ]
