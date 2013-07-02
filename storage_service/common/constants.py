
from locations.models import LocalFilesystem, NFS
from locations.forms import LocalFilesystemForm, NFSForm


########################## SPACES ##########################

# Mapping between access protocol and protocol specific fields
PROTOCOL = {}
# BUG: fields: [] works for obj_create, but includes everything in model_to_dict
PROTOCOL['FS'] = {'model': LocalFilesystem,
                  'form': LocalFilesystemForm,
                  'fields': [] }
PROTOCOL['NFS'] = {'model': NFS,
                   'form': NFSForm,
                   'fields': ['manually_mounted',
                              'remote_name',
                              'remote_path',
                              'version'] }
