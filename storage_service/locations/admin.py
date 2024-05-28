from django.contrib import admin

from .models import NFS
from .models import Event
from .models import LocalFilesystem
from .models import Location
from .models import Package
from .models import Pipeline
from .models import Space

admin.site.register(Event)
admin.site.register(Package)
admin.site.register(LocalFilesystem)
admin.site.register(Location)
admin.site.register(NFS)
admin.site.register(Pipeline)
admin.site.register(Space)
