from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0016_mirror_location_aip_replication")]

    operations = [
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
                ],
            ),
        )
    ]
