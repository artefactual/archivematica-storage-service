from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [("locations", "0006_package_related_packages")]

    operations = [
        migrations.CreateModel(
            name="Dataverse",
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
                    "host",
                    models.CharField(
                        help_text=b"Hostname of the Dataverse instance. Eg. apitest.dataverse.org",
                        max_length=256,
                    ),
                ),
                (
                    "api_key",
                    models.CharField(
                        help_text=b"API key for Dataverse instance. Eg. b84d6b87-7b1e-4a30-a374-87191dbbbe2d",
                        max_length=50,
                    ),
                ),
                (
                    "agent_name",
                    models.CharField(
                        help_text=b"Agent name for premis:agentName in Archivematica",
                        max_length=50,
                    ),
                ),
                (
                    "agent_type",
                    models.CharField(
                        help_text=b"Agent type for premis:agentType in Archivematica",
                        max_length=50,
                    ),
                ),
                (
                    "agent_identifier",
                    models.CharField(
                        help_text=b"URI agent identifier for premis:agentIdentifierValue in Archivematica",
                        max_length=256,
                    ),
                ),
                (
                    "space",
                    models.OneToOneField(
                        to="locations.Space", to_field="uuid", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={"verbose_name": "Dataverse"},
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
                    (b"FEDORA", b"FEDORA via SWORD2"),
                    (b"FS", b"Local Filesystem"),
                    (b"LOM", b"LOCKSS-o-matic"),
                    (b"NFS", b"NFS"),
                    (b"PIPE_FS", b"Pipeline Local Filesystem"),
                    (b"SWIFT", b"Swift"),
                ],
            ),
            preserve_default=True,
        ),
    ]
