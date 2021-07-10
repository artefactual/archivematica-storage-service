from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0018_create_async_table")]

    operations = [
        migrations.CreateModel(
            name="S3",
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
                    "endpoint_url",
                    models.CharField(
                        help_text="S3 Endpoint URL. Eg. https://s3.amazonaws.com",
                        max_length=2048,
                        verbose_name="S3 Endpoint URL",
                    ),
                ),
                (
                    "access_key_id",
                    models.CharField(
                        max_length=64, verbose_name="Access Key ID to authenticate"
                    ),
                ),
                (
                    "secret_access_key",
                    models.CharField(
                        max_length=256,
                        verbose_name="Secret Access Key to authenticate with",
                    ),
                ),
                (
                    "region",
                    models.CharField(
                        help_text="Region in S3. Eg. us-east-2",
                        max_length=64,
                        verbose_name="Region",
                    ),
                ),
            ],
            options={"verbose_name": "S3"},
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
            model_name="s3",
            name="space",
            field=models.OneToOneField(
                to="locations.Space", to_field="uuid", on_delete=models.CASCADE
            ),
        ),
    ]
