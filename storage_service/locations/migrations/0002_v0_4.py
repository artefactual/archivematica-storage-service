from django.db import models, migrations
import jsonfield.fields
import locations.models


class Migration(migrations.Migration):

    dependencies = [("locations", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Lockssomatic",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "au_size",
                    models.BigIntegerField(
                        help_text=b"Size in bytes of an Allocation Unit",
                        null=True,
                        verbose_name=b"AU Size",
                        blank=True,
                    ),
                ),
                (
                    "sd_iri",
                    models.URLField(
                        help_text=b"URL of LOCKSS-o-matic service document IRI, eg. http://lockssomatic.example.org/api/sword/2.0/sd-iri",
                        max_length=256,
                        verbose_name=b"Service Document IRI",
                    ),
                ),
                (
                    "collection_iri",
                    models.CharField(
                        help_text=b"URL to post the packages to, eg. http://lockssomatic.example.org/api/sword/2.0/col-iri/12",
                        max_length=256,
                        null=True,
                        verbose_name=b"Collection IRI",
                        blank=True,
                    ),
                ),
                (
                    "content_provider_id",
                    models.CharField(
                        help_text=b"On-Behalf-Of value when communicating with LOCKSS-o-matic",
                        max_length=32,
                        verbose_name=b"Content Provider ID",
                    ),
                ),
                (
                    "external_domain",
                    models.URLField(
                        help_text=b"Base URL for this server that LOCKSS will be able to access.  Probably the URL for the home page of the Storage Service.",
                        verbose_name=b"Externally available domain",
                    ),
                ),
                (
                    "checksum_type",
                    models.CharField(
                        help_text=b"Checksum type to send to LOCKSS-o-matic for verification.  Eg. md5, sha1, sha256",
                        max_length=64,
                        null=True,
                        verbose_name=b"Checksum type",
                        blank=True,
                    ),
                ),
                (
                    "keep_local",
                    models.BooleanField(
                        default=True,
                        help_text=b"If checked, keep a local copy even after the AIP is stored in the LOCKSS network.",
                        verbose_name=b"Keep local copy?",
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={},
            bases=(models.Model,),
        ),
        migrations.AlterModelOptions(
            name="localfilesystem", options={"verbose_name": "Local Filesystem"}
        ),
        migrations.AlterModelOptions(
            name="nfs", options={"verbose_name": "Network File System (NFS)"}
        ),
        migrations.AlterModelOptions(
            name="pipelinelocalfs", options={"verbose_name": "Pipeline Local FS"}
        ),
        migrations.AddField(
            model_name="package",
            name="misc_attributes",
            field=jsonfield.fields.JSONField(
                default={},
                help_text=b"For storing flexible, often Space-specific, attributes",
                null=True,
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="space",
            name="staging_path",
            field=models.TextField(
                default="/var/archivematica/storage_service/",
                help_text=b"Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.",
                validators=[locations.models.space.validate_space_path],
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="location",
            name="purpose",
            field=models.CharField(
                help_text=b"Purpose of the space.  Eg. AIP storage, Transfer source",
                max_length=2,
                choices=[
                    (b"TS", b"Transfer Source"),
                    (b"AS", b"AIP Storage"),
                    (b"DS", b"DIP Storage"),
                    (b"BL", b"Transfer Backlog"),
                    (b"CP", b"Currently Processing"),
                    (b"SS", b"Storage Service Internal Processing"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="package",
            name="size",
            field=models.IntegerField(
                default=0, help_text=b"Size in bytes of the package"
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="package",
            name="status",
            field=models.CharField(
                default=b"FAIL",
                help_text=b"Status of the package in the storage service.",
                max_length=8,
                choices=[
                    (b"PENDING", b"Upload Pending"),
                    (b"STAGING", b"Staged on Storage Service"),
                    (b"UPLOADED", b"Uploaded"),
                    (b"VERIFIED", b"Verified"),
                    (b"FAIL", b"Failed"),
                    (b"DEL_REQ", b"Delete requested"),
                    (b"DELETED", b"Deleted"),
                ],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text=b"How the space can be accessed.",
                max_length=8,
                choices=[
                    (b"FS", b"Local Filesystem"),
                    (b"NFS", b"NFS"),
                    (b"PIPE_FS", b"Pipeline Local Filesystem"),
                    (b"LOM", b"LOCKSS-o-matic"),
                ],
            ),
            preserve_default=True,
        ),
    ]
