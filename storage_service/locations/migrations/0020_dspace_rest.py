from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0019_s3")]

    operations = [
        migrations.CreateModel(
            name="DSpaceREST",
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
                    "ds_rest_url",
                    models.URLField(
                        help_text="URL of the REST API. E.g. http://demo.dspace.org/rest",
                        max_length=256,
                        verbose_name="REST URL",
                    ),
                ),
                (
                    "ds_user",
                    models.CharField(
                        help_text="DSpace username to authenticate as",
                        max_length=64,
                        verbose_name="User",
                    ),
                ),
                (
                    "ds_password",
                    models.CharField(
                        help_text="DSpace password to authenticate with",
                        max_length=64,
                        verbose_name="Password",
                    ),
                ),
                (
                    "ds_dip_collection",
                    models.CharField(
                        help_text="UUID of default DSpace collection for the DIP to be deposited to",
                        max_length=64,
                        verbose_name="Default DSpace DIP collection id",
                    ),
                ),
                (
                    "ds_aip_collection",
                    models.CharField(
                        help_text="UUID of default DSpace collection for the AIP to be deposited to",
                        max_length=64,
                        verbose_name="Default DSpace AIP collection id",
                    ),
                ),
                (
                    "as_url",
                    models.URLField(
                        help_text="URL of ArchivesSpace server. E.g. http://sandbox.archivesspace.org:8089/ (default port 8089 if omitted)",
                        max_length=256,
                        verbose_name="ArchivesSpace URL",
                        blank=True,
                    ),
                ),
                (
                    "as_user",
                    models.CharField(
                        help_text="ArchivesSpace username to authenticate as",
                        max_length=64,
                        verbose_name="ArchivesSpace user",
                        blank=True,
                    ),
                ),
                (
                    "as_password",
                    models.CharField(
                        help_text="ArchivesSpace password to authenticate with",
                        max_length=64,
                        verbose_name="ArchivesSpace password",
                        blank=True,
                    ),
                ),
                (
                    "as_repository",
                    models.CharField(
                        help_text="Identifier of the default ArchivesSpace repository",
                        max_length=64,
                        verbose_name="Default ArchivesSpace repository",
                        blank=True,
                    ),
                ),
                (
                    "as_archival_object",
                    models.CharField(
                        help_text="Identifier of the default ArchivesSpace archival object",
                        max_length=64,
                        verbose_name="Default ArchivesSpace archival object",
                        blank=True,
                    ),
                ),
                (
                    "verify_ssl",
                    models.BooleanField(
                        default=True,
                        help_text="If checked, HTTPS requests will verify the SSL certificates",
                        verbose_name="Verify SSL certificates?",
                    ),
                ),
                (
                    "upload_to_tsm",
                    models.BooleanField(
                        default=False,
                        help_text="If checked, will attempt to send the AIP to the Tivoli Storage Manager using command-line client dsmc, which must be installed manually",
                        verbose_name="Send AIP to Tivoli Storage Manager?",
                    ),
                ),
            ],
            options={"verbose_name": "DSpace via REST API"},
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text="How the space can be accessed.",
                max_length=8,
                verbose_name="Access protocol",
                choices=[
                    (b"ARKIVUM", "Arkivum"),
                    (b"DV", "Dataverse"),
                    (b"DC", "DuraCloud"),
                    (b"DSPACE", "DSpace via SWORD2 API"),
                    (b"DSPC_RST", "DSpace via REST API"),
                    (b"FEDORA", "FEDORA via SWORD2"),
                    (b"GPG", "GPG encryption on Local Filesystem"),
                    (b"FS", "Local Filesystem"),
                    (b"LOM", "LOCKSS-o-matic"),
                    (b"NFS", "NFS"),
                    (b"PIPE_FS", "Pipeline Local Filesystem"),
                    (b"SWIFT", "Swift"),
                    (b"S3", "S3"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="dspacerest",
            name="space",
            field=models.OneToOneField(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
        ),
    ]
