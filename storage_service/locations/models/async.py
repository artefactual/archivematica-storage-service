from __future__ import absolute_import
# stdlib, alphabetical
import cPickle
import logging

# Core Django, alphabetical
from django.db import models
from django.utils import six
from django.utils.translation import ugettext_lazy as _l

__all__ = ('Async',)

LOGGER = logging.getLogger(__name__)


class Async(models.Model):
    """ Stores information about currently running asynchronous tasks. """

    completed = models.BooleanField(default=False,
        verbose_name=_l('Completed'),
        help_text=_l("True if this task has finished."))

    was_error = models.BooleanField(default=False,
        verbose_name=_l('Was there an exception?'),
        help_text=_l("True if this task threw an exception."))

    _result = models.BinaryField(null=True, db_column='result')

    _error = models.BinaryField(null=True, db_column='error')

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    completed_time = models.DateTimeField(null=True)

    @property
    def result(self):
        result = self._result
        if isinstance(result, six.memoryview):
            result = str(result)
        return cPickle.loads(result)

    @result.setter
    def result(self, value):
        self._result = cPickle.dumps(value)

    @property
    def error(self):
        return cPickle.loads(self._error)

    @error.setter
    def error(self, value):
        self._error = cPickle.dumps(str(type(value)) + ": " + str(value))

    class Meta:
        verbose_name = _l("Async")
        app_label = 'locations'

    def __unicode__(self):
        return str(self.id)
