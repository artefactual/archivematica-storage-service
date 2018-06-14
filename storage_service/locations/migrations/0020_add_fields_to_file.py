# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0019_s3'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='format_name',
            field=models.TextField(max_length=128, blank=True),
        ),
        migrations.AddField(
            model_name='file',
            name='ingestion_time',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='file',
            name='normalized',
            field=models.BooleanField(
                default=False,
                help_text=b'Whether or not file has been normalized'),
        ),
        migrations.AddField(
            model_name='file',
            name='pronom_id',
            field=models.TextField(max_length=128, blank=True),
        ),
        migrations.AddField(
            model_name='file',
            name='size',
            field=models.IntegerField(
                default=0,
                help_text=b'Size in bytes of the file'),
        ),
        migrations.AddField(
            model_name='file',
            name='valid',
            field=models.NullBooleanField(
                default=None,
                help_text=b'Indicates whether validation has occurred and, if'
                ' so, whether or not the file was assessed as valid'),
        ),
        migrations.AlterField(
            model_name='location',
            name='pipeline',
            field=models.ManyToManyField(
                help_text='The Archivematica instance using this location.',
                to='locations.Pipeline', verbose_name='Pipeline',
                through='locations.LocationPipeline', blank=True),
        ),
    ]
