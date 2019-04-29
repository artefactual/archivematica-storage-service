# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [("locations", "0020_dspace_rest")]

    operations = [
        migrations.AddField(
            model_name="package",
            name="accession_id",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="package",
            name="extra_metadata",
            field=jsonfield.fields.JSONField(
                default={},
                help_text="Stores additional metadata about a package, for access in receipt files and callbacks.",
                null=True,
                blank=True,
            ),
        ),
    ]
