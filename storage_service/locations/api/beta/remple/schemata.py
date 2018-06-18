from collections import OrderedDict
import re

from formencode.schema import Schema
from formencode.validators import Int, FancyValidator, Regex, Invalid

from .constants import formencode_field2openapi_type


class NotUsed(Exception):
    pass


class OpenAPISchema(object):

    def __init__(self, formencode_schema, config):
        self.formencode_schema = formencode_schema
        self.config = config

    def extract_parameters(self):
        """Return a list of OrderedDicts describing this schema as an OpenAPI
        parameter.
        """
        parameters = []
        for parameter_name, formencode_cls in (
                self.formencode_schema.fields.items()):
            config = self.config.get(parameter_name, {})
            parameter = OrderedDict()
            schema = OrderedDict()
            parameter['in'] = config.get('in', 'query')
            parameter['name'] = parameter_name
            parameter['required'] = config.get(
                'required', formencode_cls.not_empty)
            schema['type'] = formencode_field2openapi_type.get(
                type(formencode_cls), 'string')
            minimum = formencode_cls.min
            if minimum is not None:
                schema['minimum'] = minimum
            parameter['schema'] = schema
            description = config.get('description', None)
            if description is not None:
                parameter['description'] = description
            default = config.get('default', NotUsed)
            if default != NotUsed:
                schema['default'] = default
            parameters.append(parameter)
        return parameters


class PaginatorSchema(Schema):
    allow_extra_fields = True
    filter_extra_fields = False
    items_per_page = Int(not_empty=True, min=1)
    page = Int(not_empty=True, min=1)


PaginatorOpenAPISchema = OpenAPISchema(
    PaginatorSchema,
    {
        'page': {
            'description': 'The page number to return.',
            'required': False,
            'default': 1,
        },
        'items_per_page': {
            'description': 'The maximum number of items to return.',
            'required': False,
            'default': 10,
        }
    })

schemata = (PaginatorOpenAPISchema,)


UUID = Regex(
    r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-'
    r'[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')


def camel_case2lower_space(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1).lower()


class ResourceURI(FancyValidator):
    """Validator for input values that are primary keys of model objects. Value
    must be the pk of an existing model of the type specified in the
    ``model_cls`` kwarg. If valid, the model object is returned. Example
    usage: ResourceURI(model_cls=models.Package).
    """

    messages = {
        'invalid_model':
        'There is no %(model_name_eng)s with pk %(id)s.'
    }

    def _convert_to_python(self, value, state):
        if value in ('', None):
            return None
        else:
            pk = filter(None, value.split('/'))[-1]
            pk_validator = getattr(self, 'pk_validator', UUID)
            pk = pk_validator().to_python(pk, state)
            pk_attr = getattr(self, 'pk', 'uuid')
            model_cls = self.model_cls
            try:
                model_object = model_cls.objects.get(
                    **{pk_attr: pk})
            except model_cls.DoesNotExist:
                model_name_eng = camel_case2lower_space(
                    self.model_cls.__name__)
                raise Invalid(
                    self.message('invalid_model', state, id=pk,
                                 model_name_eng=model_name_eng),
                    value, state)
            else:
                return model_object


__all__ = ('schemata', 'PaginatorSchema', 'ResourceURI')
