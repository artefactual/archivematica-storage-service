from django.contrib import admin
from .models import Event, Package, LocalFilesystem, Location, NFS, Pipeline, Space

admin.site.register(Event)
admin.site.register(Package)
admin.site.register(LocalFilesystem)
admin.site.register(Location)
admin.site.register(NFS)
admin.site.register(Pipeline)
admin.site.register(Space)
