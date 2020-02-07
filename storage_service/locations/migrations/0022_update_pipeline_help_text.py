# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from __future__ import absolute_import
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0021_alter_callback")]

    operations = [
        migrations.AlterField(
            model_name="pipeline",
            name="remote_name",
            field=models.CharField(
                default=None,
                max_length=256,
                blank=True,
                help_text="Base URL of the pipeline server for making API calls.",
                null=True,
                verbose_name="Remote name",
            ),
        )
    ]
