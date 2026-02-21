from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0037_django42"),
    ]

    operations = [
        migrations.AlterField(
            model_name="location",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("AR", "AIP Recovery"),
                    ("AS", "AIP Storage"),
                    ("CP", "Currently Processing"),
                    ("DS", "DIP Storage"),
                    ("SD", "FEDORA Deposits"),
                    ("SS", "Storage Service Internal Processing"),
                    ("TS", "Transfer Source"),
                    ("RP", "Replicator"),
                ],
                help_text="Purpose of the space.  Eg. AIP storage, Transfer source",
                max_length=2,
                verbose_name="Purpose",
            ),
        ),
    ]
