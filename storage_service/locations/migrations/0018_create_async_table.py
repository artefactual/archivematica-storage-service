from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("locations", "0017_gpg_space_minor_migration")]

    operations = [
        migrations.CreateModel(
            name="Async",
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
                (
                    "completed",
                    models.BooleanField(
                        default=False,
                        help_text="True if this task has finished.",
                        verbose_name="Completed",
                    ),
                ),
                (
                    "was_error",
                    models.BooleanField(
                        default=False,
                        help_text="True if this task threw an exception.",
                        verbose_name="Was there an exception?",
                    ),
                ),
                ("_result", models.BinaryField(null=True, db_column="result")),
                ("_error", models.BinaryField(null=True, db_column="error")),
                ("created_time", models.DateTimeField(auto_now_add=True)),
                ("updated_time", models.DateTimeField(auto_now=True)),
                ("completed_time", models.DateTimeField(null=True)),
            ],
            options={"verbose_name": "Async"},
            bases=(models.Model,),
        )
    ]
