# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Location'
        db.create_table(u'locations_location', (
            ('id', self.gf('django.db.models.fields.CharField')(max_length=36, primary_key=True)),
            ('purpose', self.gf('django.db.models.fields.CharField')(max_length=2)),
            ('access_protocol', self.gf('django.db.models.fields.CharField')(max_length=6)),
            ('path', self.gf('django.db.models.fields.TextField')()),
            ('quota', self.gf('django.db.models.fields.BigIntegerField')()),
            ('used', self.gf('django.db.models.fields.BigIntegerField')(default=0)),
        ))
        db.send_create_signal(u'locations', ['Location'])


    def backwards(self, orm):
        # Deleting model 'Location'
        db.delete_table(u'locations_location')


    models = {
        u'locations.location': {
            'Meta': {'object_name': 'Location'},
            'access_protocol': ('django.db.models.fields.CharField', [], {'max_length': '6'}),
            'id': ('django.db.models.fields.CharField', [], {'max_length': '36', 'primary_key': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {}),
            'purpose': ('django.db.models.fields.CharField', [], {'max_length': '2'}),
            'quota': ('django.db.models.fields.BigIntegerField', [], {}),
            'used': ('django.db.models.fields.BigIntegerField', [], {'default': '0'})
        }
    }

    complete_apps = ['locations']