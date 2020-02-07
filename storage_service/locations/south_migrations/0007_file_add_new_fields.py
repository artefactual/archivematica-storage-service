# -*- coding: utf-8 -*-

from __future__ import absolute_import
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding field 'File.package'
        db.add_column(
            u"locations_file",
            "package",
            self.gf("django.db.models.fields.related.ForeignKey")(
                to=orm["locations.Package"], null=True
            ),
            keep_default=False,
        )

        # Adding field 'File.source_package'
        db.add_column(
            u"locations_file",
            "source_package",
            self.gf("django.db.models.fields.TextField")(default="", blank=True),
            keep_default=False,
        )

        # Adding field 'File.accessionid'
        db.add_column(
            u"locations_file",
            "accessionid",
            self.gf("django.db.models.fields.TextField")(default="", blank=True),
            keep_default=False,
        )

        # Adding field 'File.origin'
        db.add_column(
            u"locations_file",
            "origin",
            self.gf("django.db.models.fields.CharField")(
                default="", max_length=36, blank=True
            ),
            keep_default=False,
        )

    def backwards(self, orm):
        # Deleting field 'File.package'
        db.delete_column(u"locations_file", "package_id")

        # Deleting field 'File.source_package'
        db.delete_column(u"locations_file", "source_package")

        # Deleting field 'File.accessionid'
        db.delete_column(u"locations_file", "accessionid")

        # Deleting field 'File.origin'
        db.delete_column(u"locations_file", "origin")

    models = {
        u"auth.group": {
            "Meta": {"object_name": "Group"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "name": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "80"},
            ),
            "permissions": (
                "django.db.models.fields.related.ManyToManyField",
                [],
                {
                    "to": u"orm['auth.Permission']",
                    "symmetrical": "False",
                    "blank": "True",
                },
            ),
        },
        u"auth.permission": {
            "Meta": {
                "ordering": "(u'content_type__app_label', u'content_type__model', u'codename')",
                "unique_together": "((u'content_type', u'codename'),)",
                "object_name": "Permission",
            },
            "codename": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "100"},
            ),
            "content_type": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": u"orm['contenttypes.ContentType']"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "name": ("django.db.models.fields.CharField", [], {"max_length": "50"}),
        },
        u"auth.user": {
            "Meta": {"object_name": "User"},
            "date_joined": (
                "django.db.models.fields.DateTimeField",
                [],
                {"default": "datetime.datetime.now"},
            ),
            "email": (
                "django.db.models.fields.EmailField",
                [],
                {"max_length": "75", "blank": "True"},
            ),
            "first_name": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "30", "blank": "True"},
            ),
            "groups": (
                "django.db.models.fields.related.ManyToManyField",
                [],
                {"to": u"orm['auth.Group']", "symmetrical": "False", "blank": "True"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "is_active": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "True"},
            ),
            "is_staff": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "is_superuser": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "last_login": (
                "django.db.models.fields.DateTimeField",
                [],
                {"default": "datetime.datetime.now"},
            ),
            "last_name": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "30", "blank": "True"},
            ),
            "password": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "128"},
            ),
            "user_permissions": (
                "django.db.models.fields.related.ManyToManyField",
                [],
                {
                    "to": u"orm['auth.Permission']",
                    "symmetrical": "False",
                    "blank": "True",
                },
            ),
            "username": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "30"},
            ),
        },
        u"contenttypes.contenttype": {
            "Meta": {
                "ordering": "('name',)",
                "unique_together": "(('app_label', 'model'),)",
                "object_name": "ContentType",
                "db_table": "'django_content_type'",
            },
            "app_label": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "100"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "model": ("django.db.models.fields.CharField", [], {"max_length": "100"}),
            "name": ("django.db.models.fields.CharField", [], {"max_length": "100"}),
        },
        "locations.callback": {
            "Meta": {"object_name": "Callback"},
            "enabled": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "True"},
            ),
            "event": ("django.db.models.fields.CharField", [], {"max_length": "15"}),
            "expected_status": (
                "django.db.models.fields.IntegerField",
                [],
                {"default": "200"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "method": ("django.db.models.fields.CharField", [], {"max_length": "10"}),
            "uri": ("django.db.models.fields.CharField", [], {"max_length": "1024"}),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "36", "blank": "True"},
            ),
        },
        "locations.duracloud": {
            "Meta": {"object_name": "Duracloud"},
            "duraspace": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "64"},
            ),
            "host": ("django.db.models.fields.CharField", [], {"max_length": "256"}),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "password": ("django.db.models.fields.CharField", [], {"max_length": "64"}),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
            "user": ("django.db.models.fields.CharField", [], {"max_length": "64"}),
        },
        "locations.event": {
            "Meta": {"object_name": "Event"},
            "admin_id": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": u"orm['auth.User']", "null": "True", "blank": "True"},
            ),
            "event_reason": ("django.db.models.fields.TextField", [], {}),
            "event_type": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "8"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "package": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Package']", "to_field": "'uuid'"},
            ),
            "pipeline": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Pipeline']", "to_field": "'uuid'"},
            ),
            "status": ("django.db.models.fields.CharField", [], {"max_length": "8"}),
            "status_reason": (
                "django.db.models.fields.TextField",
                [],
                {"null": "True", "blank": "True"},
            ),
            "status_time": (
                "django.db.models.fields.DateTimeField",
                [],
                {"auto_now": "True", "blank": "True"},
            ),
            "store_data": (
                "django.db.models.fields.TextField",
                [],
                {"null": "True", "blank": "True"},
            ),
            "user_email": (
                "django.db.models.fields.EmailField",
                [],
                {"max_length": "254"},
            ),
            "user_id": ("django.db.models.fields.PositiveIntegerField", [], {}),
        },
        "locations.fedora": {
            "Meta": {"object_name": "Fedora"},
            "fedora_name": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256"},
            ),
            "fedora_password": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256"},
            ),
            "fedora_user": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "64"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
        },
        "locations.file": {
            "Meta": {"object_name": "File"},
            "accessionid": ("django.db.models.fields.TextField", [], {"blank": "True"}),
            "checksum": (
                "django.db.models.fields.TextField",
                [],
                {"max_length": "128"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "name": ("django.db.models.fields.TextField", [], {"max_length": "1000"}),
            "origin": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "36", "blank": "True"},
            ),
            "package": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Package']", "null": "True"},
            ),
            "source_id": (
                "django.db.models.fields.TextField",
                [],
                {"max_length": "128"},
            ),
            "source_package": (
                "django.db.models.fields.TextField",
                [],
                {"blank": "True"},
            ),
            "stored": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
        },
        "locations.localfilesystem": {
            "Meta": {"object_name": "LocalFilesystem"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
        },
        "locations.location": {
            "Meta": {"object_name": "Location"},
            "description": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "enabled": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "True"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "pipeline": (
                "django.db.models.fields.related.ManyToManyField",
                [],
                {
                    "symmetrical": "False",
                    "to": "orm['locations.Pipeline']",
                    "null": "True",
                    "through": "orm['locations.LocationPipeline']",
                    "blank": "True",
                },
            ),
            "purpose": ("django.db.models.fields.CharField", [], {"max_length": "2"}),
            "quota": (
                "django.db.models.fields.BigIntegerField",
                [],
                {"default": "None", "null": "True", "blank": "True"},
            ),
            "relative_path": ("django.db.models.fields.TextField", [], {}),
            "space": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Space']", "to_field": "'uuid'"},
            ),
            "used": ("django.db.models.fields.BigIntegerField", [], {"default": "0"}),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
        },
        "locations.locationpipeline": {
            "Meta": {"object_name": "LocationPipeline"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "location": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Location']", "to_field": "'uuid'"},
            ),
            "pipeline": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Pipeline']", "to_field": "'uuid'"},
            ),
        },
        "locations.lockssomatic": {
            "Meta": {"object_name": "Lockssomatic"},
            "au_size": (
                "django.db.models.fields.BigIntegerField",
                [],
                {"null": "True", "blank": "True"},
            ),
            "checksum_type": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "64", "null": "True", "blank": "True"},
            ),
            "collection_iri": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256", "null": "True", "blank": "True"},
            ),
            "content_provider_id": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "32"},
            ),
            "external_domain": (
                "django.db.models.fields.URLField",
                [],
                {"max_length": "200"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "keep_local": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "True"},
            ),
            "sd_iri": ("django.db.models.fields.URLField", [], {"max_length": "256"}),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
        },
        "locations.nfs": {
            "Meta": {"object_name": "NFS"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "manually_mounted": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "remote_name": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256"},
            ),
            "remote_path": ("django.db.models.fields.TextField", [], {}),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
            "version": (
                "django.db.models.fields.CharField",
                [],
                {"default": "'nfs4'", "max_length": "64"},
            ),
        },
        "locations.package": {
            "Meta": {"object_name": "Package"},
            "current_location": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Location']", "to_field": "'uuid'"},
            ),
            "current_path": ("django.db.models.fields.TextField", [], {}),
            "description": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "misc_attributes": (
                "jsonfield.fields.JSONField",
                [],
                {"default": "{}", "null": "True", "blank": "True"},
            ),
            "origin_pipeline": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {
                    "to": "orm['locations.Pipeline']",
                    "to_field": "'uuid'",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "package_type": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "8"},
            ),
            "pointer_file_location": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {
                    "blank": "True",
                    "related_name": "'+'",
                    "to_field": "'uuid'",
                    "null": "True",
                    "to": "orm['locations.Location']",
                },
            ),
            "pointer_file_path": (
                "django.db.models.fields.TextField",
                [],
                {"null": "True", "blank": "True"},
            ),
            "size": ("django.db.models.fields.IntegerField", [], {"default": "0"}),
            "status": (
                "django.db.models.fields.CharField",
                [],
                {"default": "'FAIL'", "max_length": "8"},
            ),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
        },
        "locations.packagedownloadtask": {
            "Meta": {"object_name": "PackageDownloadTask"},
            "download_completion_time": (
                "django.db.models.fields.DateTimeField",
                [],
                {"default": "None", "null": "True", "blank": "True"},
            ),
            "downloads_attempted": (
                "django.db.models.fields.IntegerField",
                [],
                {"default": "0"},
            ),
            "downloads_completed": (
                "django.db.models.fields.IntegerField",
                [],
                {"default": "0"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "package": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {"to": "orm['locations.Package']", "to_field": "'uuid'"},
            ),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
        },
        "locations.packagedownloadtaskfile": {
            "Meta": {"object_name": "PackageDownloadTaskFile"},
            "completed": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "failed": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
            "filename": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "task": (
                "django.db.models.fields.related.ForeignKey",
                [],
                {
                    "related_name": "'download_file_set'",
                    "to_field": "'uuid'",
                    "to": "orm['locations.PackageDownloadTask']",
                },
            ),
            "url": ("django.db.models.fields.TextField", [], {}),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
        },
        "locations.pipeline": {
            "Meta": {"object_name": "Pipeline"},
            "api_key": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "api_username": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "description": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "enabled": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "True"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "remote_name": (
                "django.db.models.fields.CharField",
                [],
                {
                    "default": "None",
                    "max_length": "256",
                    "null": "True",
                    "blank": "True",
                },
            ),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36"},
            ),
        },
        "locations.pipelinelocalfs": {
            "Meta": {"object_name": "PipelineLocalFS"},
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "remote_name": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "256"},
            ),
            "remote_user": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "64"},
            ),
            "space": (
                "django.db.models.fields.related.OneToOneField",
                [],
                {
                    "to": "orm['locations.Space']",
                    "to_field": "'uuid'",
                    "unique": "True",
                },
            ),
        },
        "locations.space": {
            "Meta": {"object_name": "Space"},
            "access_protocol": (
                "django.db.models.fields.CharField",
                [],
                {"max_length": "8"},
            ),
            u"id": ("django.db.models.fields.AutoField", [], {"primary_key": "True"}),
            "last_verified": (
                "django.db.models.fields.DateTimeField",
                [],
                {"default": "None", "null": "True", "blank": "True"},
            ),
            "path": (
                "django.db.models.fields.TextField",
                [],
                {"default": "''", "blank": "True"},
            ),
            "size": (
                "django.db.models.fields.BigIntegerField",
                [],
                {"default": "None", "null": "True", "blank": "True"},
            ),
            "staging_path": ("django.db.models.fields.TextField", [], {}),
            "used": ("django.db.models.fields.BigIntegerField", [], {"default": "0"}),
            "uuid": (
                "django.db.models.fields.CharField",
                [],
                {"unique": "True", "max_length": "36", "blank": "True"},
            ),
            "verified": (
                "django.db.models.fields.BooleanField",
                [],
                {"default": "False"},
            ),
        },
    }

    complete_apps = ["locations"]
