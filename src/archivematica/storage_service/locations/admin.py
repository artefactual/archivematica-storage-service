from django.contrib import admin

from archivematica.storage_service.locations.models import NFS
from archivematica.storage_service.locations.models import Event
from archivematica.storage_service.locations.models import LocalFilesystem
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models import Pipeline
from archivematica.storage_service.locations.models import Space

admin.site.register(Event)
admin.site.register(Package)
admin.site.register(LocalFilesystem)
admin.site.register(Location)
admin.site.register(NFS)
admin.site.register(Pipeline)
admin.site.register(Space)
