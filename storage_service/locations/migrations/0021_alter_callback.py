from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0020_dspace_rest")]

    operations = [
        migrations.AddField(
            model_name="callback",
            name="body",
            field=models.TextField(
                help_text="Body content for each request. Set the 'Content-type' header accordingly.",
                null=True,
                verbose_name="Body",
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="callback",
            name="headers",
            field=models.TextField(
                help_text="Headers for each request.",
                null=True,
                verbose_name="Headers",
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="callback",
            name="event",
            field=models.CharField(
                help_text="Type of event when this callback should be executed.",
                max_length=15,
                verbose_name="Event",
                choices=[
                    (b"post_store", "Post-store AIP (source files)"),
                    (b"post_store_aip", "Post-store AIP"),
                    (b"post_store_aic", "Post-store AIC"),
                    (b"post_store_dip", "Post-store DIP"),
                ],
            ),
        ),
    ]
