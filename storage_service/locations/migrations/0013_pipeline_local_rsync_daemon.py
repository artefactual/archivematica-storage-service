from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0012_dspace_archive_format")]

    operations = [
        migrations.AddField(
            model_name="pipelinelocalfs",
            name="assume_rsync_daemon",
            field=models.BooleanField(
                default=False,
                verbose_name="Assume remote host serving files with rsync daemon",
                help_text="If checked, will use rsync daemon-style commands instead of the default rsync with remote shell transport",
            ),
        ),
        migrations.AddField(
            model_name="pipelinelocalfs",
            name="rsync_password",
            field=models.CharField(
                max_length=64,
                blank=True,
                default="",
                help_text="RSYNC_PASSWORD value (rsync daemon)",
            ),
        ),
    ]
