from django.contrib import admin
from .models import File, LocalFilesystem, Location, Samba, Space

admin.site.register(File)
admin.site.register(LocalFilesystem)
admin.site.register(Location)
admin.site.register(Samba)
admin.site.register(Space)
