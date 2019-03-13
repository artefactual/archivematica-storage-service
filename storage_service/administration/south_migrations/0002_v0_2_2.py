# -*- coding: utf-8 -*-

from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding model 'Settings'
        db.create_table(
            u"administration_settings",
            (
                (u"id", self.gf("django.db.models.fields.AutoField")(primary_key=True)),
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
        db.send_create_signal(u"administration", ["Settings"])

    def backwards(self, orm):
        # Deleting model 'Settings'
        db.delete_table(u"administration_settings")

    models = {
        u"administration.settings": {
            "Meta": {"object_name": "Settings"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
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
