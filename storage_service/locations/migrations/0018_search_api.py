# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0017_gpg_space_minor_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='file_type',
            field=models.CharField(
                max_length=8, null=True,
                choices=[(b'AIP', b'AIP'), (b'transfer', b'Transfer')]),
        ),
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
            model_name='space',
            name='access_protocol',
            field=models.CharField(
                help_text='How the space can be accessed.',
                max_length=8,
                verbose_name='Access protocol',
                choices=[(b'ARKIVUM', 'Arkivum'),
                         (b'DV', 'Dataverse'),
                         (b'DC', 'DuraCloud'),
                         (b'DSPACE', 'DSpace via SWORD2 API'),
                         (b'FEDORA', 'FEDORA via SWORD2'),
                         (b'GPG', 'GPG encryption on Local Filesystem'),
                         (b'FS', 'Local Filesystem'),
                         (b'LOM', 'LOCKSS-o-matic'),
                         (b'NFS', 'NFS'),
                         (b'PIPE_FS', 'Pipeline Local Filesystem'),
                         (b'SWIFT', 'Swift')]),
        ),
    ]
