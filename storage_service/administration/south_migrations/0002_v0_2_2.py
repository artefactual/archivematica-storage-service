from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding model 'Settings'
        db.create_table(
            "administration_settings",
            (
                ("id", self.gf("django.db.models.fields.AutoField")(primary_key=True)),
                (
                    "name",
                    self.gf("django.db.models.fields.CharField")(
                        unique=True, max_length=255
                    ),
                ),
                (
                    "value",
                    self.gf("django.db.models.fields.TextField")(null=True, blank=True),
                ),
            ),
        )
        db.send_create_signal("administration", ["Settings"])

    def backwards(self, orm):
        # Deleting model 'Settings'
        db.delete_table("administration_settings")

    models = {
        "administration.settings": {
            "Meta": {"object_name": "Settings"},
            "id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "name": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "255"},
            ),
            "value": (
                "django.db.models.fields.TextField",
                [],
                {"null": "True", "blank": "True"},
            ),
        }
    }

    complete_apps = ["administration"]
