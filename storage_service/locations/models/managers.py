from __future__ import absolute_import
from django.db import models


class Enabled(models.Manager):
    """ Manager to only return enabled objects.

    Filters by disable=False if it exists, or enabled=True if it exists, or
    returns all items if neither is found.  """

    def get_queryset(self):
        try:
            self.model._meta.get_field("enabled")
        except models.FieldDoesNotExist:
            try:
                self.model._meta.get_field("disabled")
            except models.FieldDoesNotExist:
                return super(Enabled, self).get_queryset()
            else:
                return super(Enabled, self).get_queryset().filter(disabled=False)
        else:  # found enabled
            return super(Enabled, self).get_queryset().filter(enabled=True)
