from typing import List
from typing import Tuple

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies: List[Tuple[str, str]] = []

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
