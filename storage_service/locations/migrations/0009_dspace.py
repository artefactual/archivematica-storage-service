from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [("locations", "0008_fixitylog")]

    operations = [
        migrations.CreateModel(
            name="DSpace",
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
                    "sd_iri",
                    models.URLField(
                        help_text=b"URL of the service document. E.g. http://demo.dspace.org/swordv2/servicedocument",
                        max_length=256,
                        verbose_name=b"Service Document IRI",
                    ),
                ),
                (
                    "user",
                    models.CharField(
                        help_text=b"DSpace username to authenticate as", max_length=64
                    ),
                ),
                (
                    "password",
                    models.CharField(
                        help_text=b"DSpace password to authenticate with", max_length=64
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "DSpace via SWORD2 API"},
            bases=(models.Model,),
        ),
        migrations.AlterField(
            model_name="space",
            name="access_protocol",
            field=models.CharField(
                help_text=b"How the space can be accessed.",
                max_length=8,
                choices=[
                    (b"ARKIVUM", b"Arkivum"),
                    (b"DV", b"Dataverse"),
                    (b"DC", b"DuraCloud"),
                    (b"DSPACE", b"DSpace via SWORD2 API"),
                    (b"FEDORA", b"FEDORA via SWORD2"),
                    (b"FS", b"Local Filesystem"),
                    (b"LOM", b"LOCKSS-o-matic"),
                    (b"NFS", b"NFS"),
                    (b"PIPE_FS", b"Pipeline Local Filesystem"),
                    (b"SWIFT", b"Swift"),
                ],
            ),
        ),
    ]
