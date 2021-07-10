# stdlib, alphabetical
import logging

# Core Django, alphabetical
from django.db import models
from django.utils import six
from django.utils.six.moves import cPickle as pickle
from django.utils.translation import ugettext_lazy as _

__all__ = ("Async",)

LOGGER = logging.getLogger(__name__)


class Async(models.Model):
    """ Stores information about currently running asynchronous tasks. """

    completed = models.BooleanField(
        default=False,
        verbose_name=_("Completed"),
        help_text=_("True if this task has finished."),
    )

    was_error = models.BooleanField(
        default=False,
        verbose_name=_("Was there an exception?"),
        help_text=_("True if this task threw an exception."),
    )

    _result = models.BinaryField(null=True, db_column="result")

    _error = models.BinaryField(null=True, db_column="error")

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    completed_time = models.DateTimeField(null=True)

    @property
    def result(self):
        result = self._result
        if isinstance(result, six.memoryview):
            result = str(result)
        return pickle.loads(result)

    @result.setter
    def result(self, value):
        self._result = pickle.dumps(value)

    @property
    def error(self):
        error = self._error
        if isinstance(error, six.memoryview):
            error = str(error)
        return pickle.loads(error)

    @error.setter
    def error(self, value):
        self._error = pickle.dumps(str(type(value)) + ": " + str(value))

    class Meta:
        verbose_name = _("Async")
        app_label = "locations"

    def __str__(self):
        return f"{self.id}"
