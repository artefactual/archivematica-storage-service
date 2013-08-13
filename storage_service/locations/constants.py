
from .models import LocalFilesystem, NFS, PipelineLocalFS, Space
from .forms import LocalFilesystemForm, NFSForm, PipelineLocalFSForm


########################## SPACES ##########################

# Mapping between access protocol and protocol specific fields
PROTOCOL = {}
# BUG: fields: [] works for obj_create, but includes everything in model_to_dict
PROTOCOL[Space.LOCAL_FILESYSTEM] = {
    'model': LocalFilesystem,
    'form': LocalFilesystemForm,
    'fields': []
}
PROTOCOL[Space.NFS] = {
    'model': NFS,
    'form': NFSForm,
    'fields': ['manually_mounted',
               'remote_name',
               'remote_path',
               'version']
}
PROTOCOL[Space.PIPELINE_LOCAL_FS] = {
    'model': PipelineLocalFS,
    'form': PipelineLocalFSForm,
    'fields': ['remote_user',
               'remote_name']
}
