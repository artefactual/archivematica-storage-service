from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Settings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("name", models.CharField(unique=True, max_length=255)),
                ("value", models.TextField(null=True, blank=True)),
            ],
            options={},
            bases=(models.Model,),
        )
    ]
