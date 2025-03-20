from django.core.management.base import BaseCommand


class StorageServiceCommand(BaseCommand):
    def success(self, message):
        self.stdout.write(self.style.SUCCESS(message))

    def error(self, message):
        self.stdout.write(self.style.ERROR(message))

    def warning(self, message):
        self.stdout.write(self.style.WARNING(message))

    def info(self, message):
        self.stdout.write(message)
