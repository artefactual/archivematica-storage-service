from __future__ import absolute_import
from django.db import models


class Settings(models.Model):
    name = models.CharField(max_length=255, unique=True)
    value = models.TextField(null=True, blank=True)

    def __unicode__(self):
        return u"{}: {}".format(self.name, self.value)
