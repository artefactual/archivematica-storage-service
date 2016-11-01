# stdlib, alphabetical

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical


class FixityLog(models.Model):
    """ Stores fixity check success/failure and error details """

    package = models.ForeignKey('Package', to_field='uuid')
    success = models.NullBooleanField(default=False)
    error_details = models.TextField(null=True)
    datetime_reported = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fixity Log"
        app_label = 'locations'

    def __unicode__(self):
        return u"Fixity check of {package}".format(
            package=self.package)
