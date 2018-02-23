# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0017_gpg_space_minor_migration'),
    ]

    operations = [
        migrations.CreateModel(
            name='Async',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('completed', models.BooleanField(default=False, help_text=b'True if the task has finished')),
                ('was_error', models.BooleanField(default=False, help_text=b'True if the task threw an exception')),
                ('result', models.BinaryField(null=True)),
                ('error', models.BinaryField(null=True)),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('updated_time', models.DateTimeField(auto_now_add=True, auto_now=True)),
                ('completed_time', models.DateTimeField(null=True)),
            ],
            options={
                'verbose_name': 'Async',
            },
            bases=(models.Model,),
        ),
    ]
