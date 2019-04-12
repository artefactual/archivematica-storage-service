# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0023_allow_blank_aws_auth")]

    operations = [
        migrations.AddField(
            model_name='s3',
            name='bucket',
            field=models.CharField(help_text='S3 Bucket Name', max_length=64, verbose_name='S3 Bucket', blank=True),
        ),
    ]
