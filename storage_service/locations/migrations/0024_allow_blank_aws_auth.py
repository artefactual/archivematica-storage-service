from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0023_s3_bucket_field")]

    operations = [
        migrations.AlterField(
            model_name="s3",
            name="access_key_id",
            field=models.CharField(
                max_length=64, verbose_name="Access Key ID to authenticate", blank=True
            ),
        ),
        migrations.AlterField(
            model_name="s3",
            name="secret_access_key",
            field=models.CharField(
                max_length=256,
                verbose_name="Secret Access Key to authenticate with",
                blank=True,
            ),
        ),
    ]
