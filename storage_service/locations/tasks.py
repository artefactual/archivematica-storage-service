from __future__ import absolute_import

from celery import shared_task

from .models import Package


@shared_task
def move_package_to_location_task(package_uuid, location_uuid):
    package = Package.objects.get(uuid=package_uuid)
    package.move_to_location(location_uuid)
