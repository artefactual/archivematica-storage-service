import locations.api.resources as resources

from tastypie import fields


class PipelineResource(resources.PipelineResource):
    create_default_locations = fields.BooleanField(use_in=lambda x: False)
    shared_path = fields.CharField(use_in=lambda x: False)


class SpaceResource(resources.SpaceResource):
    def get_objects(self, space, path):
        return space.browse(path)


class LocationResource(resources.LocationResource):
    space = fields.ForeignKey(SpaceResource, "space")
    path = fields.CharField(attribute="full_path", readonly=True)
    description = fields.CharField(attribute="get_description", readonly=True)
    pipeline = fields.ToManyField(PipelineResource, "pipeline")

    def get_objects(self, space, path):
        return space.browse(path)


class PackageResource(resources.PackageResource):
    origin_pipeline = fields.ForeignKey(PipelineResource, "origin_pipeline")
    origin_location = fields.ForeignKey(LocationResource, None, use_in=lambda x: False)
    origin_path = fields.CharField(use_in=lambda x: False)
    current_location = fields.ForeignKey(LocationResource, "current_location")

    current_full_path = fields.CharField(attribute="full_path", readonly=True)


class AsyncResource(resources.AsyncResource):
    pass
