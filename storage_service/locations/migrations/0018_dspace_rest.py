# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0017_gpg_space_minor_migration'),
    ]

    operations = [
        migrations.CreateModel(
            name='DSpaceREST',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('rest_url', models.URLField(help_text='URL of the REST API. E.g. http://demo.dspace.org/rest', max_length=256, verbose_name='REST URL ')),
                ('user', models.CharField(help_text='DSpace username to authenticate as', max_length=64, verbose_name='User')),
                ('password', models.CharField(help_text='DSpace password to authenticate with', max_length=64, verbose_name='Password')),
                ('archive_format', models.CharField(default=b'ZIP', max_length=3, verbose_name='Archive format', choices=[(b'ZIP', b'ZIP'), (b'7Z', b'7z')])),
                ('archivesspace_archival_object', models.CharField(help_text='Number of the default ArchivesSpace archival object', max_length=64,
                                              verbose_name='Default ArchivesSpace archival object')),
                ('archivesspace_password', models.CharField(help_text='ArchivesSpace password to authenticate with', max_length=64,
                                              verbose_name='ArchivesSpace password')),
                ('archivesspace_repository', models.CharField(help_text='Number of the default ArchivesSpace repository', max_length=64,
                                              verbose_name='Default ArchivesSpace repository')),
                ('archivesspace_url', models.URLField(help_text='URL of ArchivesSpace server. E.g. http://sandbox.archivesspace.org/ (default port is 8089)', max_length=256,
                                              verbose_name='ArchivesSpace URL')),
                ('archivesspace_user', models.CharField(help_text='ArchivesSpace username to authenticate as', max_length=64,
                                              verbose_name='ArchivesSpace user')),
                ('dspace_aip_collection', models.CharField(help_text='UUID of default DSpace collection for the AIP to be deposited to', max_length=64,
                                                        verbose_name='Default DSpace AIP collection id')),
                ('dspace_dip_collection', models.CharField(help_text='UUID of default DSpace collection for the DIP to be deposited to', max_length=64,
                                                        verbose_name='Default DSpace DIP collection id')),
            ],
            options={
                'verbose_name': 'DSpace via REST API',
            },
        ),
        migrations.AlterField(
            model_name='space',
            name='access_protocol',
            field=models.CharField(help_text='How the space can be accessed.', max_length=8, verbose_name='Access protocol', choices=[(b'ARKIVUM', 'Arkivum'), (b'DV', 'Dataverse'), (b'DC', 'DuraCloud'), (b'DSPACE', 'DSpace via SWORD2 API'), (b'DSPC_RST', 'DSpace via REST API'), (b'FEDORA', 'FEDORA via SWORD2'), (b'GPG', 'GPG encryption on Local Filesystem'), (b'FS', 'Local Filesystem'), (b'LOM', 'LOCKSS-o-matic'), (b'NFS', 'NFS'), (b'PIPE_FS', 'Pipeline Local Filesystem'), (b'SWIFT', 'Swift')]),
        ),
        migrations.AddField(
            model_name='dspacerest',
            name='space',
            field=models.OneToOneField(to='locations.Space', to_field=b'uuid'),
        ),
    ]
