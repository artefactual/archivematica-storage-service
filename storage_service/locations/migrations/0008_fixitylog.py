# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from __future__ import absolute_import
from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [("locations", "0007_dataverse")]

    operations = [
        migrations.CreateModel(
            name="FixityLog",
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
                ("success", models.BooleanField(default=False)),
                ("error_details", models.TextField(null=True)),
                ("datetime_reported", models.DateTimeField(auto_now=True)),
                ("package", models.ForeignKey(to="locations.Package", to_field="uuid")),
            ],
            options={"verbose_name": "Fixity Log"},
            bases=(models.Model,),
        )
    ]
