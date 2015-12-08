# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0004_v0_7'),
    ]

    operations = [
        migrations.AddField(
            model_name='package',
            name='related_packages',
            field=models.ManyToManyField(related_name='related_packages_rel_+', to='locations.Package'),
            preserve_default=True,
        ),
    ]
