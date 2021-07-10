from south.v2 import DataMigration


class Migration(DataMigration):
    def forwards(self, orm):
        "Write your forwards methods here."
        # Note: Don't use "from appname.models import ModelName".
        # Use orm.ModelName to refer to models in this application,
        # and orm['appname.ModelName'] for models in other applications.

    def backwards(self, orm):
        "Write your backwards methods here."

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
    symmetrical = True
