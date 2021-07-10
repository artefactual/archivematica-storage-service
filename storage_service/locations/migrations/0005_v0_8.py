from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0004_v0_7")]

    operations = [
        migrations.AlterField(
            model_name="location",
            name="pipeline",
            field=models.ManyToManyField(
                help_text=b"UUID of the Archivematica instance using this location.",
                to="locations.Pipeline",
                through="locations.LocationPipeline",
                blank=True,
            ),
        )
    ]
