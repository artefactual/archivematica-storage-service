from . import forms
from . import models

# ######################## SPACES ##########################

# Mapping between access protocol and protocol specific fields
PROTOCOL = {
    models.Space.ARKIVUM: {
        "model": models.Arkivum,
        "form": forms.ArkivumForm,
        "fields": ["host", "remote_user", "remote_name"],
    },
    models.Space.DATAVERSE: {
        "model": models.Dataverse,
        "form": forms.DataverseForm,
        "fields": ["host", "agent_name", "agent_type", "agent_identifier"],
    },
    models.Space.DURACLOUD: {
        "model": models.Duracloud,
        "form": forms.DuracloudForm,
        "fields": ["host", "user", "duraspace"],
    },
    models.Space.DSPACE: {
        "model": models.DSpace,
        "form": forms.DSpaceForm,
        "fields": ["sd_iri", "user", "archive_format"],
    },
    models.Space.DSPACE_REST: {
        "model": models.DSpaceREST,
        "form": forms.DSpaceRESTForm,
        "fields": [
            "ds_rest_url",
            "ds_user",
            "ds_password",
            "ds_dip_collection",
            "ds_aip_collection",
            "as_url",
            "as_user",
            "as_password",
            "as_repository",
            "as_archival_object",
            "verify_ssl",
        ],
    },
    models.Space.FEDORA: {
        "model": models.Fedora,
        "form": forms.FedoraForm,
        "fields": ["fedora_user", "fedora_password", "fedora_name"],
    },
    models.Space.GPG: {"model": models.GPG, "form": forms.GPGForm, "fields": ["key"]},
    # BUG: fields: [] works for obj_create, but includes everything in model_to_dict
    models.Space.LOCAL_FILESYSTEM: {
        "model": models.LocalFilesystem,
        "form": forms.LocalFilesystemForm,
        "fields": [],
    },
    models.Space.LOM: {
        "model": models.Lockssomatic,
        "form": forms.LockssomaticForm,
        "fields": [
            "au_size",
            "sd_iri",
            "collection_iri",
            "content_provider_id",
            "external_domain",
            "keep_local",
            "checksum_type",
        ],
    },
    models.Space.NFS: {
        "model": models.NFS,
        "form": forms.NFSForm,
        "fields": ["manually_mounted", "remote_name", "remote_path", "version"],
    },
    models.Space.OFFLINE_REPLICA_STAGING: {
        "model": models.OfflineReplicaStaging,
        "form": forms.OfflineReplicaStagingForm,
        "fields": [],
    },
    models.Space.PIPELINE_LOCAL_FS: {
        "model": models.PipelineLocalFS,
        "form": forms.PipelineLocalFSForm,
        "fields": [
            "remote_user",
            "remote_name",
            "assume_rsync_daemon",
            "rsync_password",
        ],
    },
    models.Space.SWIFT: {
        "model": models.Swift,
        "form": forms.SwiftForm,
        "fields": [
            "auth_url",
            "auth_version",
            "username",
            "password",
            "container",
            "tenant",
            "region",
        ],
    },
    models.Space.S3: {
        "model": models.S3,
        "form": forms.S3Form,
        "fields": [
            "endpoint_url",
            "access_key_id",
            "secret_access_key",
            "region",
            "bucket",
        ],
    },
}
