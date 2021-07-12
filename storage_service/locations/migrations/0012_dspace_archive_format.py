from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0011_fixitylog_status")]

    operations = [
        migrations.AddField(
            model_name="dspace",
            name="archive_format",
            field=models.CharField(
                default="ZIP",
                max_length=3,
                verbose_name=b"Archive format",
                choices=[("ZIP", "ZIP"), ("7Z", "7z")],
            ),
        )
    ]
