from django.contrib import admin
from .models import File, LocalFilesystem, Location, NFS, Pipeline, Space

admin.site.register(File)
admin.site.register(LocalFilesystem)
admin.site.register(Location)
admin.site.register(NFS)
admin.site.register(Pipeline)
admin.site.register(Space)
