from __future__ import absolute_import
import logging

from django.contrib.auth.models import Group, Permission
from formencode.compound import Any
from formencode.foreach import ForEach
from formencode.schema import Schema
from formencode.validators import (
    Bool,
    Email,
    Int,
    IPAddress,
    OneOf,
    Regex,
    UnicodeString,
    URL,
)

from locations import models
from locations.api.beta.remple import ResourceURI


logger = logging.getLogger(__name__)


def _flatten(choices):
    return [ch[0] for ch in choices]


class PipelineSchema(Schema):
    api_key = UnicodeString(max=256)
    api_username = UnicodeString(max=256)
    description = UnicodeString(max=256)
    enabled = Bool()
    remote_name = Any(validators=[IPAddress(), URL()])


class SpaceUpdateSchema(Schema):
    size = Int(min=0)
    path = UnicodeString(max=256)
    staging_path = UnicodeString(max=256)


class SpaceCreateSchema(SpaceUpdateSchema):
    access_protocol = OneOf(
        _flatten(models.Space.ACCESS_PROTOCOL_CHOICES))


class TypeOfSpaceSchema(Schema):
    space = ResourceURI(model_cls=models.Space)


class LocalFilesystemSpaceSchema(TypeOfSpaceSchema):
    pass


class GPGSpaceSchema(TypeOfSpaceSchema):
    key = UnicodeString(max=256)


class ArkivumSpaceSchema(TypeOfSpaceSchema):
    host = UnicodeString(max=256)
    remote_user = UnicodeString(max=64)
    remote_name = UnicodeString(max=256)


class DataverseSpaceSchema(TypeOfSpaceSchema):
    host = UnicodeString(max=256)
    api_key = UnicodeString(max=50)
    agent_name = UnicodeString(max=50)
    agent_type = UnicodeString(max=50)
    agent_identifier = UnicodeString(max=256)


class DSpaceSpaceSchema(TypeOfSpaceSchema):
    sd_iri = URL(max=256)
    user = UnicodeString(max=64)
    password = UnicodeString(max=64)
    metadata_policy = UnicodeString()  # JSONField ...
    archive_format = OneOf(_flatten(models.DSpace.ARCHIVE_FORMAT_CHOICES))


class DuracloudSpaceSchema(TypeOfSpaceSchema):
    host = UnicodeString(max=256)
    user = UnicodeString(max=64)
    password = UnicodeString(max=64)
    duraspace = UnicodeString(max=64)


class FedoraSpaceSchema(TypeOfSpaceSchema):
    fedora_user = UnicodeString(max=64)
    fedora_password = UnicodeString(max=256)
    fedora_name = UnicodeString(max=256)


class LockssomaticSpaceSchema(TypeOfSpaceSchema):
    collection_iri = UnicodeString(max=256)
    content_provider_id = UnicodeString(max=32)
    checksum_type = UnicodeString(max=64)
    keep_local = Bool()
    au_size = Int()
    sd_iri = URL(max=256)
    external_domain = URL()


class NFSSpaceSchema(TypeOfSpaceSchema):
    remote_name = UnicodeString(max=256)
    remote_path = UnicodeString()
    version = UnicodeString(max=64)
    manually_mounted = Bool()


class S3SpaceSchema(TypeOfSpaceSchema):
    endpoint_url = UnicodeString(max=2048)
    access_key_id = UnicodeString(max=64)
    secret_access_key = UnicodeString(max=256)
    region = UnicodeString(max=64)


class SwiftSpaceSchema(TypeOfSpaceSchema):
    auth_url = UnicodeString(max=256)
    auth_version = UnicodeString(max=8)
    username = UnicodeString(max=64)
    password = UnicodeString(max=256)
    container = UnicodeString(max=64)
    tenant = UnicodeString(max=64)
    region = UnicodeString(max=64)


class PipelineLocalSpaceSchema(TypeOfSpaceSchema):
    remote_user = UnicodeString(max=64)
    remote_name = UnicodeString(max=256)
    assume_rsync_daemon = Bool()
    rsync_password = UnicodeString(max=64)


class LocationSchema(Schema):
    description = UnicodeString(max=256)
    purpose = OneOf(_flatten(models.Location.PURPOSE_CHOICES))
    relative_path = UnicodeString()
    quota = Int(min=0)
    enabled = Bool()
    space = ResourceURI(model_cls=models.Space)
    pipeline = ForEach(ResourceURI(model_cls=models.Pipeline))
    replicators = ForEach(ResourceURI(model_cls=models.Location))


# Note: it does not make sense to have a schema for the package resource since
# it is not truly mutable via an external API. I am leaving this for now in
# case it contains useful information in the future.
class PackageSchema(Schema):
    current_location = ResourceURI(model_cls=models.Location)
    current_path = UnicodeString()
    description = UnicodeString(max=256)
    encryption_key_fingerprint = UnicodeString(max=512)
    misc_attributes = UnicodeString()
    origin_pipeline = ResourceURI(model_cls=models.Pipeline)
    package_type = OneOf(
        _flatten(models.Package.PACKAGE_TYPE_CHOICES))
    pointer_file_location = ResourceURI(model_cls=models.Location)
    pointer_file_path = UnicodeString()
    related_packages = ForEach(ResourceURI(model_cls=models.Package))
    replicated_package = ResourceURI(model_cls=models.Package)
    size = Int(min=0)
    status = OneOf(_flatten(models.Package.STATUS_CHOICES))


class UserSchema(Schema):
    username = Regex(r'^[a-zA-Z0-9_@+\.-]+$', max=150)
    password = UnicodeString()
    first_name = UnicodeString(max=30)
    last_name = UnicodeString(max=150)
    email = Email()
    groups = ForEach(ResourceURI(model_cls=Group))
    user_permissions = ForEach(ResourceURI(model_cls=Permission))
    is_staff = Bool()
    is_active = Bool()
    is_superuser = Bool()
