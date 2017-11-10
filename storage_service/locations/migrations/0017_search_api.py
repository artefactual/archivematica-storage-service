# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0016_mirror_location_aip_replication'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='file_type',
            field=models.CharField(max_length=8, null=True, choices=[(b'AIP', b'AIP'), (b'transfer', b'Transfer')]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='format_name',
            field=models.TextField(max_length=128, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='ingestion_time',
            field=models.DateTimeField(null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='normalized',
            field=models.NullBooleanField(blank=True, default=None, null=True, help_text=b'Whether or not file has been normalized'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='pronom_id',
            field=models.TextField(max_length=128, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='size',
            field=models.IntegerField(default=0, help_text=b'Size in bytes of the file'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='file',
            name='validated',
            field=models.NullBooleanField(blank=True, default=None, null=True, help_text=b'Whether or not file has been validated'),
            preserve_default=True,
        ),
    ]
