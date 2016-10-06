# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0008_fixitylog'),
    ]

    operations = [
        migrations.CreateModel(
            name='iRODS',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('host', models.CharField(help_text='iRODS API server name or IP', max_length=256)),
                ('port', models.PositiveIntegerField(default=1247, help_text='port, default is 1247')),
                ('user', models.CharField(help_text='iRODS user', max_length=256)),
                ('password', models.CharField(help_text='Corresponding password', max_length=256)),
                ('zone', models.CharField(default=b'tempZone', help_text='iRODS zone (e.g. tempZone)', max_length=256)),
                ('resource', models.CharField(help_text=b'iRODS resource used for storing objects', max_length=256)),
                ('callback', models.CharField(help_text=b'If present a call will be made to this URL after a successful/finished move_from_storage_service() (data stored on the iRODS backend) with the destination name as argument.', max_length=512, verbose_name='Non-mandatory callback URL', blank=True)),
            ],
            options={
                'verbose_name': 'iRODS',
            },
        ),
    ]
