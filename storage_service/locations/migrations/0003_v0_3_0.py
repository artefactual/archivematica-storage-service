# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

class Migration(DataMigration):

    def forwards(self, orm):
        "Write your forwards methods here."
        # Note: Don't use "from appname.models import ModelName". 
        # Use orm.ModelName to refer to models in this application,
        # and orm['appname.ModelName'] for models in other applications.

    def backwards(self, orm):
        "Write your backwards methods here."

    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')", 'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'locations.event': {
            'Meta': {'object_name': 'Event'},
            'admin_id': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['auth.User']", 'null': 'True', 'blank': 'True'}),
            'event_reason': ('django.db.models.fields.TextField', [], {}),
            'event_type': ('django.db.models.fields.CharField', [], {'max_length': '8'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'package': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Package']", 'to_field': "'uuid'"}),
            'pipeline': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Pipeline']", 'to_field': "'uuid'"}),
            'status': ('django.db.models.fields.CharField', [], {'max_length': '8'}),
            'status_reason': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'status_time': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'store_data': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'user_email': ('django.db.models.fields.EmailField', [], {'max_length': '254'}),
            'user_id': ('django.db.models.fields.PositiveIntegerField', [], {})
        },
        u'locations.localfilesystem': {
            'Meta': {'object_name': 'LocalFilesystem'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'space': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['locations.Space']", 'to_field': "'uuid'", 'unique': 'True'})
        },
        u'locations.location': {
            'Meta': {'object_name': 'Location'},
            'description': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'pipeline': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': u"orm['locations.Pipeline']", 'null': 'True', 'through': u"orm['locations.LocationPipeline']", 'blank': 'True'}),
            'purpose': ('django.db.models.fields.CharField', [], {'max_length': '2'}),
            'quota': ('django.db.models.fields.BigIntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'relative_path': ('django.db.models.fields.TextField', [], {}),
            'space': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Space']", 'to_field': "'uuid'"}),
            'used': ('django.db.models.fields.BigIntegerField', [], {'default': '0'}),
            'uuid': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '36', 'blank': 'True'})
        },
        u'locations.locationpipeline': {
            'Meta': {'object_name': 'LocationPipeline'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'location': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Location']", 'to_field': "'uuid'"}),
            'pipeline': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Pipeline']", 'to_field': "'uuid'"})
        },
        u'locations.nfs': {
            'Meta': {'object_name': 'NFS'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'manually_mounted': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'remote_name': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'remote_path': ('django.db.models.fields.TextField', [], {}),
            'space': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['locations.Space']", 'to_field': "'uuid'", 'unique': 'True'}),
            'version': ('django.db.models.fields.CharField', [], {'default': "'nfs4'", 'max_length': '64'})
        },
        u'locations.package': {
            'Meta': {'object_name': 'Package'},
            'current_location': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Location']", 'to_field': "'uuid'"}),
            'current_path': ('django.db.models.fields.TextField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'origin_pipeline': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['locations.Pipeline']", 'to_field': "'uuid'"}),
            'package_type': ('django.db.models.fields.CharField', [], {'max_length': '8'}),
            'pointer_file_location': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'+'", 'to_field': "'uuid'", 'null': 'True', 'to': u"orm['locations.Location']"}),
            'pointer_file_path': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'size': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'status': ('django.db.models.fields.CharField', [], {'default': "'FAIL'", 'max_length': '8'}),
            'uuid': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '36', 'blank': 'True'})
        },
        u'locations.pipeline': {
            'Meta': {'object_name': 'Pipeline'},
            'description': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'uuid': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '36'})
        },
        u'locations.pipelinelocalfs': {
            'Meta': {'object_name': 'PipelineLocalFS'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'remote_name': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'remote_user': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'space': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['locations.Space']", 'to_field': "'uuid'", 'unique': 'True'})
        },
        u'locations.space': {
            'Meta': {'object_name': 'Space'},
            'access_protocol': ('django.db.models.fields.CharField', [], {'max_length': '8'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'last_verified': ('django.db.models.fields.DateTimeField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {}),
            'size': ('django.db.models.fields.BigIntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'used': ('django.db.models.fields.BigIntegerField', [], {'default': '0'}),
            'uuid': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '36', 'blank': 'True'}),
            'verified': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['locations']
    symmetrical = True
