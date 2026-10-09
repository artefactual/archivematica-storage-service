from typing import TypeVar

from django.db import models

_ModelT = TypeVar("_ModelT", bound=models.Model)


class Enabled(models.Manager[_ModelT]):
    """Manager to only return enabled objects.

    Filters by disable=False if it exists, or enabled=True if it exists, or
    returns all items if neither is found."""

    def get_queryset(self) -> models.QuerySet[_ModelT]:
        try:
            self.model._meta.get_field("enabled")
        except models.FieldDoesNotExist:
            try:
                self.model._meta.get_field("disabled")
            except models.FieldDoesNotExist:
                return super().get_queryset()
            else:
                return super().get_queryset().filter(disabled=False)
        else:  # found enabled
            return super().get_queryset().filter(enabled=True)
