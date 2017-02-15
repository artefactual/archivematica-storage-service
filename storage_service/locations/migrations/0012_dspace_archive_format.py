# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0011_fixitylog_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='dspace',
            name='archive_format',
            field=models.CharField(default=b'ZIP', max_length=3, verbose_name=b'Archive format', choices=[(b'ZIP', b'ZIP'), (b'7Z', b'7z')]),
        ),
    ]
