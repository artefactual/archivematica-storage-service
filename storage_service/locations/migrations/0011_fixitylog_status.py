from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0010_dspace_metadata_policy")]

    operations = [
        migrations.AlterField(
            model_name="fixitylog",
            name="success",
            field=models.NullBooleanField(default=False),
        )
    ]
