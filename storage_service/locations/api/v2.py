import base64

import six
from tastypie import fields

import locations.api.resources as resources


def b64encode_string(data):
    return base64.b64encode(six.ensure_binary(data)).decode("utf8")


class PipelineResource(resources.PipelineResource):
    create_default_locations = fields.BooleanField(use_in=lambda x: False)
    shared_path = fields.CharField(use_in=lambda x: False)


class SpaceResource(resources.SpaceResource):
    def get_objects(self, space, path):
        objects = space.browse(path)
        objects["entries"] = [b64encode_string(e) for e in objects["entries"]]
        objects["directories"] = [b64encode_string(d) for d in objects["directories"]]

        return objects


class LocationResource(resources.LocationResource):
    space = fields.ForeignKey(SpaceResource, "space")
    path = fields.CharField(attribute="full_path", readonly=True)
    pipeline = fields.ToManyField(PipelineResource, "pipeline")

    def decode_path(self, path):
        return base64.b64decode(path).decode("utf8")

    def get_objects(self, space, path):
        objects = space.browse(path)
        objects["entries"] = [b64encode_string(e) for e in objects["entries"]]
        objects["directories"] = [b64encode_string(d) for d in objects["directories"]]
        objects["properties"] = {
            b64encode_string(k): v for k, v in objects.get("properties", {}).items()
        }
        return objects


class PackageResource(resources.PackageResource):
    origin_pipeline = fields.ForeignKey(PipelineResource, "origin_pipeline")
    origin_location = fields.ForeignKey(LocationResource, None, use_in=lambda x: False)
    origin_path = fields.CharField(use_in=lambda x: False)
    current_location = fields.ForeignKey(LocationResource, "current_location")

    current_full_path = fields.CharField(attribute="full_path", readonly=True)


class AsyncResource(resources.AsyncResource):
    pass
