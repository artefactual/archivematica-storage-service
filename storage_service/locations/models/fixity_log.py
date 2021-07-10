# stdlib, alphabetical

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical


class FixityLog(models.Model):
    """ Stores fixity check success/failure and error details """

    package = models.ForeignKey("Package", to_field="uuid", on_delete=models.CASCADE)
    success = models.NullBooleanField(default=False)
    error_details = models.TextField(null=True)
    datetime_reported = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Fixity Log")
        app_label = "locations"

    def __str__(self):
        return _("Fixity check of %(package)s") % {"package": self.package}
