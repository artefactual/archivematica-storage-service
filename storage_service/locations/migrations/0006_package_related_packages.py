# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from __future__ import absolute_import
from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [("locations", "0005_v0_8")]

    operations = [
        migrations.AddField(
            model_name="package",
            name="related_packages",
            field=models.ManyToManyField(
                related_name="related_packages_rel_+", to="locations.Package"
            ),
            preserve_default=True,
        )
    ]
