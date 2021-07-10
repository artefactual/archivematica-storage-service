from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0015_gpg_encrypted_space")]

    operations = [
        migrations.AddField(
            model_name="location",
            name="replicators",
            field=models.ManyToManyField(
                help_text="Other locations that will be used to create replicas of the packages stored in this location",
                related_name="masters",
                verbose_name="Replicators",
                to="locations.Location",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="location",
            name="purpose",
            field=models.CharField(
                help_text="Purpose of the space.  Eg. AIP storage, Transfer source",
                max_length=2,
                verbose_name="Purpose",
                choices=[
                    (b"AR", "AIP Recovery"),
                    (b"AS", "AIP Storage"),
                    (b"CP", "Currently Processing"),
                    (b"DS", "DIP Storage"),
                    (b"SD", "FEDORA Deposits"),
                    (b"SS", "Storage Service Internal Processing"),
                    (b"BL", "Transfer Backlog"),
                    (b"TS", "Transfer Source"),
                    (b"RP", "Replicator"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="package",
            name="replicated_package",
            field=models.ForeignKey(
                related_name="replicas",
                to_field="uuid",
                blank=True,
                to="locations.Package",
                null=True,
                on_delete=models.CASCADE,
            ),
        ),
    ]
