from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0024_allow_blank_aws_auth")]

    operations = [
        migrations.AlterField(
            model_name="package",
            name="size",
            field=models.BigIntegerField(
                default=0, help_text="Size in bytes of the package"
            ),
        )
    ]
