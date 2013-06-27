
from locations.models import LocalFilesystem, NFS
from locations.forms import LocalFilesystemForm, NFSForm


########################## SPACES ##########################

# Mapping between access protocol and protocol specific fields
protocol = {}
# BUG: fields: [] works for obj_create, but includes everything in model_to_dict
protocol['FS'] = {'model': LocalFilesystem,
                  'form': LocalFilesystemForm,
                  'fields': [] }
protocol['NFS'] = {'model': NFS,
                   'form': NFSForm,
                   'fields': ['manually_mounted',
                              'remote_name',
                              'remote_path',
                              'version'] }
