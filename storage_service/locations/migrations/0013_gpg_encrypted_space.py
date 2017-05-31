# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0012_dspace_archive_format'),
    ]

    operations = [
        migrations.CreateModel(
            name='GPG',
            fields=[
                ('id', models.AutoField(verbose_name='ID',
                                        serialize=False,
                                        auto_created=True,
                                        primary_key=True)),
            ],
            options={
                'verbose_name': 'GPG encryption on Local Filesystem',
            },
        ),
        migrations.AlterField(
            model_name='space',
            name='access_protocol',
            field=models.CharField(
                help_text=b'How the space can be accessed.',
                max_length=8,
                choices=[
                    (b'ARKIVUM', b'Arkivum'),
                    (b'DV', b'Dataverse'),
                    (b'DC', b'DuraCloud'),
                    (b'DSPACE', b'DSpace via SWORD2 API'),
                    (b'FEDORA', b'FEDORA via SWORD2'),
                    (b'GPG', b'GPG encryption on Local Filesystem'),
                    (b'FS', b'Local Filesystem'),
                    (b'LOM', b'LOCKSS-o-matic'),
                    (b'NFS', b'NFS'),
                    (b'PIPE_FS', b'Pipeline Local Filesystem'),
                    (b'SWIFT', b'Swift')]),
        ),
        migrations.AddField(
            model_name='gpg',
            name='space',
            field=models.OneToOneField(to='locations.Space', to_field=b'uuid'),
        ),
        migrations.AddField(
            model_name='gpg',
            name='key',
            field=models.CharField(
                help_text=b'The GnuPG private key that will be able to decrypt'
                ' packages stored in this space.',
                max_length=256,
                verbose_name=b'GnuPG Private Key'),
        ),
        migrations.AddField(
            model_name='package',
            name='encryption_key_fingerprint',
            field=models.CharField(default=None, max_length=512, null=True, help_text='The fingerprint of the GPG key used to encrypt the package, if applicable', blank=True),
        )
    ]
