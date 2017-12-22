# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0017_gpg_space_minor_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pipeline',
            name='remote_name',
            field=models.CharField(default=None, max_length=256, blank=True, help_text="URL, host name or IP address of the pipeline server for making API calls. If a valid URL is not provided, the 'http' scheme will be assumed. For example, 'archivematica-dashboard:8642' will be treated as 'http://archivematica-dashboard:8642'.", null=True, verbose_name='Remote name'),
        ),
    ]
