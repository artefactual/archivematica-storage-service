from django.db import migrations
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [("locations", "0009_dspace")]

    operations = [
        migrations.AddField(
            model_name="dspace",
            name="metadata_policy",
            field=jsonfield.fields.JSONField(
                default=[],
                help_text=b'Policy for restricted access metadata policy. Must be specified as a list of objects in JSON. This will override existing policies. Example: [{"action":"READ","groupId":"5","rpType":"TYPE_CUSTOM"}]',
                null=True,
                verbose_name=b"Restricted metadata policy",
                blank=True,
            ),
        )
    ]
