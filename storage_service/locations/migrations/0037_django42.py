# Generated by Django 4.2.5 on 2023-09-14 19:23
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0036_archipelago"),
    ]

    operations = [
        migrations.AlterField(
            model_name="package",
            name="related_packages",
            field=models.ManyToManyField(
                related_name="related", to="locations.package"
            ),
        ),
    ]