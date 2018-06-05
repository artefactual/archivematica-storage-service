from __future__ import absolute_import
import logging

from formencode.compound import Any
from formencode.foreach import ForEach
from formencode.schema import Schema
from formencode.validators import (
    Int,
    Invalid,
    IPAddress,
    OneOf,
    Bool,
    UnicodeString,
    URL,
)

from locations import models
from locations.api.v3.remple import ValidModelObject


logger = logging.getLogger(__name__)


def _flatten(choices):
    return [ch[0] for ch in choices]



class PipelineSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    api_key = UnicodeString(max=256)
    api_username = UnicodeString(max=256)
    description = UnicodeString(max=256)
    enabled = Bool()
    remote_name = Any(validators=[IPAddress(), URL()])


class SpaceUpdateSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    size = Int(min=0)
    path = UnicodeString(max=256)
    staging_path = UnicodeString(max=256)


class SpaceCreateSchema(SpaceUpdateSchema):
    allow_extra_fields = True
    filter_extra_fields = True

    access_protocol = OneOf(
        _flatten(models.Space.ACCESS_PROTOCOL_CHOICES))


class LocationSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = True

    description = UnicodeString(max=256)
    purpose = OneOf(_flatten(models.Location.PURPOSE_CHOICES))
    relative_path = UnicodeString()
    quota = Int(min=0)
    enabled = Bool()
    space = ValidModelObject(model_cls=models.Space)
    pipeline = ForEach(ValidModelObject(model_cls=models.Pipeline))
    replicators = ForEach(ValidModelObject(model_cls=models.Location))


# Note: it does not make sense to have a schema for the package resource since
# it is not truly mutable via an external API. I am leaving this for now in
# case it contains useful information in the future.
class PackageSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = True
    current_location = ValidModelObject(model_cls=models.Location)
    current_path = UnicodeString()
    description = UnicodeString(max=256)
    encryption_key_fingerprint = UnicodeString(max=512)
    misc_attributes = UnicodeString()
    origin_pipeline = ValidModelObject(model_cls=models.Pipeline)
    package_type = OneOf(
        _flatten(models.Package.PACKAGE_TYPE_CHOICES))
    pointer_file_location = ValidModelObject(model_cls=models.Location)
    pointer_file_path = UnicodeString()
    related_packages = ForEach(ValidModelObject(model_cls=models.Package))
    replicated_package = ValidModelObject(model_cls=models.Package)
    size = Int(min=0)
    status = OneOf(_flatten(models.Package.STATUS_CHOICES))
