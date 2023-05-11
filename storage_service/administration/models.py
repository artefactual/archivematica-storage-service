from django.db import models


class Settings(models.Model):
    name = models.CharField(max_length=255, unique=True)
    value = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.name}: {self.value}"
