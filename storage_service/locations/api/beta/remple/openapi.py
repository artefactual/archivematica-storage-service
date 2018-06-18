from collections import OrderedDict
import json
import logging
import yaml
try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper
from yaml.representer import SafeRepresenter

from django.db.models.fields.related import (
    ForeignKey,
    ManyToManyRel,
    ManyToManyField,
    ManyToOneRel,
    OneToOneRel,
)
from django.db.models.fields import NOT_PROVIDED
from formencode.foreach import ForEach
from formencode.compound import Any
from formencode.validators import OneOf

from .schemata import schemata
from .resources import Resources
from .constants import (
    django_field2openapi_type,
    django_field2openapi_format,
    python_type2openapi_type,
    formencode_field2openapi_type,
    formencode_field2openapi_format,
)
from .querybuilder import QueryBuilder
from .schemata import ResourceURI


logger = logging.getLogger(__name__)


def dict_representer(dumper, data):
    return dumper.represent_dict(data.iteritems())


def yaml_dump(obj):
    """Allows us to create YAML from Python OrderedDict instances and also have
    Python strings and unicode objects correctly represented. From
    https://gist.github.com/oglops/c70fb69eef42d40bed06
    """
    Dumper.add_representer(OrderedDict, dict_representer)
    Dumper.add_representer(str, SafeRepresenter.represent_str)
    Dumper.add_representer(unicode, SafeRepresenter.represent_unicode)
    # Cf. http://signal0.com/2013/02/06/disabling_aliases_in_pyyaml.html
    Dumper.ignore_aliases = lambda self, data: True
    return yaml.dump(obj, Dumper=Dumper, default_flow_style=False)


OPENAPI_VERSION = '3.0.0'
SCHEMAS_ABS_PATH = '#/components/schemas/'
ERROR_SCHEMA_NAME = 'ErrorSchema'
PAGINATOR_SCHEMA_NAME = 'PaginatorSchema'


class CustomEndPoint(object):
    """A descriptor for defining a custom API end point."""

    def __init__(self, path, http_method, action, method_name, summary='',
                 description='', tags=None, parameters=None, schemata=None,
                 responses=None, request_body=None):
        self.path = path
        self.http_method = http_method
        self.action = action
        self.method_name = method_name
        self.summary = summary
        self.description = description
        self.tags = tags or []
        self.parameters = parameters or []
        self.request_body = request_body or {}
        self.responses = responses or {}
        self.schemata = schemata or {}

    def __get__(self, instance, owner):
        return self


class OpenAPI(object):

    def __init__(self, api_version='0.1.0', service_name='My Service',
                 path_prefix='/api/'):
        self.api_version = api_version
        self.service_name = service_name
        self.path_prefix = path_prefix

    def generate_open_api_spec(self):
        """Generate and OpenAPI specification for this API.

        Returns a Python OrderedDict that can be converted to a YAML file which
        describes this ``OpenAPI`` instance.
        """
        return OrderedDict([
            ('openapi', OPENAPI_VERSION),
            ('info', self._get_api_info()),
            ('servers', self._get_api_servers()),
            ('security', self._get_api_security()),
            ('components', OrderedDict([
                ('securitySchemes', self._get_api_security_schemes()),
                ('parameters', self._get_api_remple_parameters()),
                ('schemas', self._get_schemas()),
            ])),
            ('paths', self._get_paths()),
            ('tags', self._get_tags()),

        ])

    def _get_dflt_server_description(self):
        return 'The default server for the {}.'.format(self.service_name)

    def _get_api_description(self):
        return 'An API for the {}.'.format(self.service_name)

    def _get_api_title(self):
        return '{} API'.format(self.service_name)

    def _get_tags(self):
        tags = []
        for resource_name, resource_cfg in sorted(self.resources.items()):
            resource_cls = resource_cfg['resource_cls']
            description = 'Access to the {} resource.'.format(
                resource_name.lower().replace('_', ' '))
            model_docstring = resource_cls.model_cls.__doc__.strip()
            if model_docstring.startswith(
                    '{}('.format(resource_cls.model_cls.__name__)):
                model_docstring = None
            if model_docstring:
                description += ' {}'.format(model_docstring)
            tags.append(OrderedDict([
                ('name', self.inflp.plural(resource_name)),
                ('description', description),
            ]))
        return tags

    def _get_paths(self):
        paths = {}
        for resource_name, resource_cfg in sorted(self.resources.items()):
            pk_patt = resource_cfg.get('pk_patt', 'pk')
            resource_cls = resource_cfg['resource_cls']
            rsrc_collection_name = self.inflp.plural(resource_name)
            self._set_crud_paths(paths, resource_name, resource_cls, pk_patt,
                                 rsrc_collection_name)
            if resource_cfg.get('searchable', True):
                self._set_search_paths(paths, resource_name, resource_cls,
                                       pk_patt, rsrc_collection_name)
            self._set_custom_paths(paths, resource_name, resource_cls, pk_patt,
                                   rsrc_collection_name)
        return paths

    def _set_crud_paths(self, paths, resource_name, resource_cls, pk_patt,
                        rsrc_collection_name):
        for action in self.RESOURCE_ACTIONS:
            # Read-only resources need no mutating paths
            if (not issubclass(resource_cls, Resources) and
                    action in self.MUTATING_ACTIONS):
                continue
            http_method = self.ACTIONS2METHODS.get(
                action, self.DEFAULT_METHOD).lower()
            operation_id = _get_operation_id(action, resource_name)
            path_params = None
            if action in self.COLLECTION_TARGETING:
                path = get_collection_targeting_openapi_path(
                    rsrc_collection_name)
            elif action in self.MEMBER_TARGETING:
                path, path_params = get_member_targeting_openapi_path(
                    resource_name, rsrc_collection_name, pk_patt, resource_cls)
            elif action == 'new':
                path = get_collection_targeting_openapi_path(
                    rsrc_collection_name, modifiers=['new'])
            else:  # edit is default case
                path, path_params = get_member_targeting_openapi_path(
                    resource_name, rsrc_collection_name, pk_patt, resource_cls,
                    modifiers=['edit'])
            if path_params:
                path_dict = paths.setdefault(path, {'parameters': path_params})
            else:
                path_dict = paths.setdefault(path, {})
            responses_meth = '_get_{}_responses'.format(action)
            parameters_meth = '_get_{}_parameters'.format(action)
            request_body_meth = '_get_{}_request_body'.format(action)
            parameters = getattr(self, parameters_meth, lambda x: None)(
                resource_name)
            request_body = getattr(self, request_body_meth, lambda x: None)(
                resource_name)
            summary, description = _summarize(
                action, resource_name, rsrc_collection_name)
            path_dict[http_method] = OrderedDict([
                ('summary', summary),
                ('description', description),
                ('operationId', operation_id),
            ])
            if parameters:
                path_dict[http_method]['parameters'] = parameters
            if request_body:
                path_dict[http_method]['requestBody'] = request_body
            path_dict[http_method]['responses'] = getattr(
                self, responses_meth)(resource_name)
            path_dict[http_method]['tags'] = [rsrc_collection_name]

    def _set_custom_paths(self, paths, resource_name, resource_cls, pk_patt,
                          rsrc_collection_name):
        """Set an attribute on dict ``paths`` for each custom endpoint
        configured on ``resource_cls``.
        """
        for custom_endpoint in self._get_custom_endpoints(resource_cls):
            http_method = custom_endpoint.http_method
            operation_id = _get_operation_id(
                custom_endpoint.action, resource_name)
            path = '/{}/{}'.format(rsrc_collection_name, custom_endpoint.path)
            path_dict = {
                http_method: OrderedDict([
                    ('operationId', operation_id),
                    ('summary', custom_endpoint.summary),
                    ('description', custom_endpoint.description),
                ])
            }
            for attr in ('parameters', 'request_body', 'responses', 'tags'):
                val = getattr(custom_endpoint, attr)
                if val:
                    path_dict[http_method][attr] = val
            paths[path] = path_dict

    def _get_search_request_body_examples(self, resource_name):
        """Note: unfortunately, these examples will not be displayed in the
        Swagger UI since that functionality is not implemented yet. See
        https://github.com/swagger-api/swagger-ui/issues/3771.
        """
        if resource_name == 'package':
            array_search_example = {
                'paginator': {'page': 1, 'items_per_page': 10},
                'query': {
                    'filter': [
                        'and', [['description', 'like', '%a%'],
                                ['not', ['description', 'like', 'T%']],
                                ['or', [['size', '<', 1000],
                                        ['size', '>', 512]]]]]}}
            object_search_example = {
                'paginator': {'page': 1, 'items_per_page': 10},
                'query': {
                    'filter': {
                        'conjunction': 'and',
                        'complement': [{'attribute': 'description',
                                        'relation': 'like',
                                        'value': '%a%'},
                                       {'negation': 'not',
                                        'complement': {'attribute': 'description',
                                                       'relation': 'like',
                                                       'value': 'T%'}},
                                       {'conjunction': 'or',
                                        'complement': [{'attribute': 'size',
                                                        'relation': '<',
                                                        'value': 1000},
                                                       {'attribute': 'size',
                                                        'relation': '>',
                                                        'value': 512}]}]}}}
            return {'ArraySearchOverPackagesExample': array_search_example,
                    'ObjectSearchOverPackagesExample': object_search_example}

    def _set_search_paths(self, paths, resource_name, resource_cls, pk_patt,
                          rsrc_collection_name):
        for action in ('search_post', 'new_search'):
            http_method = {'search_post': 'post', 'new_search': 'get'}.get(
                action, 'search')
            operation_id = _get_operation_id(action, resource_name)
            modifiers = {'search_post': ['search'],
                         'new_search': ['new_search']}.get(
                             action, [])
            path = get_collection_targeting_openapi_path(
                rsrc_collection_name, modifiers=modifiers)
            path_dict = paths.setdefault(path, {})
            responses_meth = '_get_{}_responses'.format(action)
            parameters_meth = '_get_{}_parameters'.format(action)
            request_body_meth = '_get_{}_request_body'.format(action)
            request_body_examples_meth = '_get_{}_request_body_examples'.format(
                action)
            parameters = getattr(self, parameters_meth, lambda x: None)(
                resource_name)
            request_body_examples = getattr(
                self, request_body_examples_meth, lambda x: None)(resource_name)
            request_body_meth = getattr(self, request_body_meth, None)
            request_body = None
            if request_body_meth:
                request_body = request_body_meth(
                    resource_name, examples=request_body_examples)
            summary, description = _summarize(
                action, resource_name, rsrc_collection_name)
            path_dict[http_method] = OrderedDict([
                ('summary', summary),
                ('description', description),
                ('operationId', operation_id),
            ])
            if parameters:
                path_dict[http_method]['parameters'] = parameters
            if request_body:
                path_dict[http_method]['requestBody'] = request_body
            path_dict[http_method]['responses'] = getattr(
                self, responses_meth)(resource_name)
            path_dict[http_method]['tags'] = [rsrc_collection_name]

    # =========================================================================
    # Schema name getters
    # =========================================================================

    def _get_read_schema_name(self, resource_name):
        return '{}View'.format(resource_name.capitalize())

    def _get_create_schema_name(self, resource_name):
        return '{}Create'.format(resource_name.capitalize())

    def _get_update_schema_name(self, resource_name):
        return '{}Update'.format(resource_name.capitalize())

    def _get_edit_schema_name(self, resource_name):
        return 'EditA{}'.format(resource_name.capitalize())

    def _get_new_schema_name(self, resource_name):
        return 'New{}'.format(resource_name.capitalize())

    def _get_paginated_schema_name(self, resource_name):
        return 'PaginatedSubsetOf{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_search_schema_name(self, resource_name):
        return 'SearchOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_query_schema_name(self, resource_name):
        return 'SearchQueryOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_filter_schema_name(self, resource_name):
        return 'FilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_object_filter_schema_name(self, resource_name):
        return 'ObjectFilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_array_filter_schema_name(self, resource_name):
        return 'ArrayFilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_new_search_schema_name(self, resource_name):
        return 'DataForNewSearchOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_related_filter_schema_name(self, resource_name, attribute):
        return 'FilterOver{}{}'.format(
            self.inflp.plural(resource_name).capitalize(),
            attribute.lower().capitalize())

    def _get_coordinative_filter_schema_name(self, resource_name):
        return 'CoordinativeFilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_negative_filter_schema_name(self, resource_name):
        return 'NegativeFilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    def _get_simple_filter_schema_name(self, resource_name):
        return 'SimpleFilterOver{}'.format(
            self.inflp.plural(resource_name).capitalize())

    # =========================================================================
    # Schema path getters
    # =========================================================================

    def _get_read_schema_path(self, resource_name):
        return schema_name2path(self._get_read_schema_name(resource_name))

    def _get_create_schema_path(self, resource_name):
        return schema_name2path(self._get_create_schema_name(resource_name))

    def _get_update_schema_path(self, resource_name):
        return schema_name2path(self._get_update_schema_name(resource_name))

    def _get_edit_schema_path(self, resource_name):
        return schema_name2path(self._get_edit_schema_name(resource_name))

    def _get_paginated_schema_path(self, resource_name):
        return schema_name2path(self._get_paginated_schema_name(resource_name))

    def _get_new_schema_path(self, resource_name):
        return schema_name2path(self._get_new_schema_name(resource_name))

    def _get_search_schema_path(self, resource_name):
        return schema_name2path(self._get_search_schema_name(resource_name))

    def _get_query_schema_path(self, resource_name):
        return schema_name2path(self._get_query_schema_name(resource_name))

    def _get_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_filter_schema_name(resource_name))

    def _get_object_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_object_filter_schema_name(resource_name))

    def _get_array_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_array_filter_schema_name(resource_name))

    def _get_coordinative_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_coordinative_filter_schema_name(
            resource_name))

    def _get_negative_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_negative_filter_schema_name(
            resource_name))

    def _get_simple_filter_schema_path(self, resource_name):
        return schema_name2path(self._get_simple_filter_schema_name(
            resource_name))

    def _get_related_filter_schema_path(self, resource_name, attribute):
        return schema_name2path(self._get_related_filter_schema_name(
            resource_name, attribute))

    def _get_related_filter_schema_paths_refs(self, resource_name,
                                              resource_cfg):
        return [
            {'$ref':
             self._get_related_filter_schema_path(resource_name, attribute)}
            for attribute, _
            in self._get_relational_attributes(resource_name, resource_cfg)]

    def _get_new_search_schema_path(self, resource_name):
        return schema_name2path(self._get_new_search_schema_name(resource_name))

    def _get_paginator_schema_path(self):
        return schema_name2path(PAGINATOR_SCHEMA_NAME)

    # =========================================================================
    # Response getters
    # =========================================================================

    def _get_create_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "create" action on
        resource ``resource_name``.
        """
        return OrderedDict([
            ('201', get_ref_response(
                description='Creation of a new {} succeeded.'.format(
                    resource_name),
                ref=self._get_read_schema_path(resource_name))),
            ('400', get_ref_response(
                description='Creation of a new {} failed.'.format(
                    resource_name),
                ref=get_error_schema_path())),
        ])

    def _get_delete_responses(self, resource_name):
        return OrderedDict([
            ('200', get_ref_response(
                description='Deletion of the {} resource succeeded.'.format(
                    resource_name),
                ref=self._get_read_schema_path(resource_name))),
            ('404', get_ref_response(
                description='Deletion of the {} resource failed because there'
                            ' is no {} with the specified pk.'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
            ('403', get_ref_response(
                description='Deletion of the {} resource failed because user is'
                            ' forbidden from performing this action'.format(
                                resource_name),
                ref=get_error_schema_path())),
        ])

    def _get_edit_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "edit" action on
        resource ``resource_name``.
        """
        return OrderedDict([
            ('200', get_ref_response(
                description='Request for the data needed to edit a(n) {}'
                            ' resource succeeded.'.format(resource_name),
                ref=self._get_edit_schema_path(resource_name))),
            ('404', get_ref_response(
                description='Request for the data needed to edit a(n) {}'
                            ' failed because there is no {} resource with the'
                            ' specified pk'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
            ('403', get_ref_response(
                description='Request for the data needed to edit a(n) {}'
                            ' failed because the user is forbidden from editing'
                            ' this {} resource.'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
        ])

    def _get_index_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "index" action on
        resource ``resource_name``.
        """
        rsrc_collection_name = self.inflp.plural(resource_name)
        return OrderedDict([
            ('200', get_ref_response(
                description='Request for a collection of {} succeeded.'.format(
                    rsrc_collection_name),
                ref=self._get_paginated_schema_path(resource_name))),
            ('400', get_ref_response(
                description='Request for a collection of {} failed.'.format(
                    rsrc_collection_name),
                ref=get_error_schema_path())),
        ])

    def _get_new_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "new" action on
        resource ``resource_name``.
        """
        return OrderedDict([
            ('200', get_ref_response(
                description='Request for the data needed to create a'
                            ' new {} resource succeeded.'.format(resource_name),
                ref=self._get_new_schema_path(resource_name))),
        ])

    def _get_show_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "show" action on
        resource ``resource_name``.
        """
        return OrderedDict([
            ('200', get_ref_response(
                description='Request for a single {} succeeded.'.format(
                    resource_name),
                ref=self._get_read_schema_path(resource_name))),
            ('404', get_ref_response(
                description='Request for a single {} failed because there is no'
                            ' {} resource with the specified pk.'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
            ('403', get_ref_response(
                description='Request for a single {} failed because the user is'
                            ' forbidden from viewing this {} resource.'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
        ])

    def _get_update_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "update" action on
        resource ``resource_name``.
        """
        return OrderedDict([
            ('200', get_ref_response(
                description='Updating of an existing {} resource'
                            ' succeeded.'.format(resource_name),
                ref=self._get_edit_schema_path(resource_name))),
            ('404', get_ref_response(
                description='Updating of an existing {} resource failed because'
                            ' there is no {} with the specified pk.'.format(
                                resource_name, resource_name),
                ref=get_error_schema_path())),
            ('403', get_ref_response(
                description='Updating of an existing {} resource failed because'
                            ' the user is forbidden from updating this'
                            ' {} resource.'.format(resource_name, resource_name),
                ref=get_error_schema_path())),
            ('400', get_ref_response(
                description='Updating of an existing {} resource'
                            ' failed.'.format(resource_name),
                ref=get_error_schema_path())),
        ])

    def _get_search_responses(self, resource_name):
        """Return an OpenAPI ``responses`` object for the "search" action on
        resource ``resource_name``.
        """
        rsrc_collection_name = self.inflp.plural(resource_name)
        return OrderedDict([
            ('200', get_ref_response(
                description='Search across all {} succeeded.'.format(
                    rsrc_collection_name),
                ref=self._get_paginated_schema_path(resource_name))),
            ('400', get_ref_response(
                description='Search across all {} failed.'.format(
                    rsrc_collection_name),
                ref=get_error_schema_path())),
        ])

    def _get_search_post_responses(self, resource_name):
        return self._get_search_responses(resource_name)

    def _get_new_search_responses(self, resource_name):
        rsrc_collection_name = self.inflp.plural(resource_name)
        return OrderedDict([
            ('200', get_ref_response(
                description='Request to get the data needed to'
                            ' search across all {} succeeded.'.format(
                                rsrc_collection_name),
                ref=self._get_new_search_schema_path(resource_name))),
        ])

    # =========================================================================
    # Request body getters
    # =========================================================================

    def _get_create_request_body(self, resource_name):
        return OrderedDict([
            ('description', 'JSON object required to create a new {}'.format(
                resource_name)),
            ('required', True),
            ('content', {
                'application/json': {
                    'schema': {
                        '$ref':
                        self._get_create_schema_path(resource_name)
                    }
                }
            }),
        ])

    def _get_update_request_body(self, resource_name):
        return OrderedDict([
            ('description', 'JSON object required to update an existing'
                            ' {}'.format(resource_name)),
            ('required', True),
            ('content', {
                'application/json': {
                    'schema': {
                        '$ref':
                        self._get_update_schema_path(resource_name)
                    }
                }
            }),
        ])

    def _get_search_request_body(self, resource_name, examples=None):
        rsrc_collection_name = self.inflp.plural(resource_name)
        application_json = OrderedDict([
            ('schema', {'$ref':
                        self._get_search_schema_path(resource_name)}),
        ])
        if examples:
            application_json['example'] = examples
        return OrderedDict([
            ('description', 'JSON object required to search over all {}'.format(
                rsrc_collection_name)),
            ('required', True),
            ('content', {'application/json': application_json}),
        ])

    def _get_search_post_request_body(self, resource_name, examples=None):
        return self._get_search_request_body(resource_name, examples=examples)

    def _get_index_parameters(self, *args):
        """Return an OpenAPI ``parameters`` object for the "index" action."""
        return [
            {'$ref': '#/components/parameters/items_per_page'},
            {'$ref': '#/components/parameters/page'},
            {'$ref': '#/components/parameters/order_by_attribute'},
            {'$ref': '#/components/parameters/order_by_subattribute'},
            {'$ref': '#/components/parameters/order_by_direction'},
        ]

    def to_yaml(self, open_api_spec):
        """Return the input OrderedDict as a YAML string."""
        return yaml_dump(open_api_spec)

    def to_json(self, open_api_spec):
        """Return the input OrderedDict as a JSON string."""
        return json.dumps(open_api_spec)

    def _get_api_info(self):
        """Return an OrderedDict for the top-level ``info`` attribute."""
        return OrderedDict([
            ('version', self.api_version),
            ('title', self._get_api_title()),
            ('description', self._get_api_description()),
        ])

    def get_dflt_server_path(self):
        return '{}{}'.format(
            self.path_prefix, self.get_api_version_slug())

    def _get_api_servers(self):
        """Return a list of OrderedDicts for the top-level ``servers``
        attribute.
        """
        return [
            OrderedDict([
                ('url', self.get_dflt_server_path()),
                ('description', self._get_dflt_server_description()),
            ]),
        ]

    def _get_api_security(self):
        """Return a list of OrderedDicts for the top-level ``security``
        attribute.
        """
        return [
            OrderedDict([('ApiKeyAuth', [])]),
        ]

    def _get_api_security_schemes(self):
        """Return an OrderedDict for the ``components.securitySchemes``
        attribute.
        """
        return OrderedDict([
            ('ApiKeyAuth', OrderedDict([
                ('type', 'apiKey'),
                ('in', 'header'),
                ('name', 'Authorization'),
                # Note: the value of this header must be of the form
                # ``ApiKey <username>:<api_key>``.
                # TODO: the OpenAPI spec does not allow a pattern here ...
                # ('pattern', r'ApiKey (?<username>\w+):(?<api_key>\w+)')
            ])),
        ])

    def _get_api_remple_parameters(self):
        """Return an OrderedDict of OrderedDicts for OpenAPI
        ``components.parameters``; these are for the Remple-internal
        internal schemata like the paginator.
        """
        parameters = OrderedDict()
        for schema in schemata:
            for parameter in schema.extract_parameters():
                parameter_name = parameter['name']
                parameters[parameter_name] = parameter
        for parameter_name, parameter in self._get_order_by_parameters().items():
            parameters[parameter_name] = parameter
        return parameters

    def _get_order_by_parameters(self):
        """Return a dict of OpenAPI query ``parameters`` for ordering the
        results of an idnex request.
        """
        return {
            'order_by_attribute': OrderedDict([
                ('in', 'query'),
                ('name', 'order_by_attribute'),
                ('schema', {'type': 'string'}),
                ('description', 'Attribute of the resource that'
                                ' view results should be ordered by.'),
                ('required', False),
            ]),
            'order_by_subattribute': OrderedDict([
                ('in', 'query'),
                ('name', 'order_by_subattribute'),
                ('schema', {'type': 'string'}),
                ('required', False),
                ('description', 'Attribute of the related attribute'
                                ' order_by_attribute of the resource'
                                ' that view results should be'
                                ' ordered by.'),
            ]),
            'order_by_direction': OrderedDict([
                ('in', 'query'),
                ('name', 'order_by_direction'),
                ('schema', OrderedDict([
                    ('type', 'string'),
                    ('enum', [obd for obd in QueryBuilder.order_by_directions
                              if obd]),
                ])),
                ('required', False),
                ('description', 'The direction of the ordering; omitting this'
                                ' parameter means ascending direction.'),
            ])
        }

    def _get_error_schema(self):
        return OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('error', OrderedDict([
                    ('type', 'string'),
                ])),
            ])),
            ('required', ['error']),
        ])

    def _get_custom_endpoints(self, resource_cls):
        """Return the custom endpoints defined on ``resource_cls``.
        """
        ret = []
        for attr_name in dir(resource_cls):
            if attr_name.startswith('_'):
                continue
            custom_endpoint = getattr(resource_cls, attr_name)
            if isinstance(custom_endpoint, CustomEndPoint):
                ret.append(custom_endpoint)
        return ret

    def _get_cust_endpt_schemata(self, resource_name, resource_cfg):
        """Return an interable of custom endpoint schema names and schemata for
        custom endpoints defined on the resource class.
        """
        ret = []
        for custom_endpoint in self._get_custom_endpoints(
                resource_cfg['resource_cls']):
            for schema_name, schema in custom_endpoint.schemata.items():
                ret.append((schema_name, schema))
        return ret

    def _get_schemas(self):
        """Return an OpenAPI ``schemas`` OrderedDict.

        It contains a "View", a "Create", and an "Update" schema for each
        resource in ``self.resources``, e.g., ``LocationView``,
        ``LocationCreate``, and ``LocationUpdate``. The create and update
        schemata are only included if the resources is not read-only. The view
        schema is constructed by introspecting the Django model, while the
        create and update schemata are constructed by introspecting the relevant
        Formencode schemata attached as class attributes on the resource class.
        """
        schemas = OrderedDict([
            ('ErrorSchema', self._get_error_schema()),
            ('PaginatorSchema', self._get_paginator_schema()),
        ])
        for resource_name, resource_cfg in sorted(self.resources.items()):
            read_schema_name, read_schema = self._get_read_schema(
                resource_name, resource_cfg)
            schemas[read_schema_name] = read_schema
            paginated_schema_name, paginated_schema = (
                self._get_paginated_subset_schema(
                    resource_name, resource_cfg, read_schema))
            schemas[paginated_schema_name] = paginated_schema
            for cust_endpt_schema_name, cust_endpt_schema in (
                    self._get_cust_endpt_schemata(resource_name, resource_cfg)):
                schemas[cust_endpt_schema_name] = cust_endpt_schema
            # Only mutable resources need the following schemata
            if issubclass(resource_cfg['resource_cls'], Resources):
                create_schema_name, create_schema = self._get_create_schema(
                    resource_name, resource_cfg, read_schema)
                schemas[create_schema_name] = create_schema
                update_schema_name, update_schema = self._get_update_schema(
                    resource_name, resource_cfg, read_schema)
                schemas[update_schema_name] = update_schema
                new_schema_name, new_schema = (
                    self._get_new_schema(resource_name, resource_cfg,
                                         read_schema))
                schemas[new_schema_name] = new_schema
                edit_schema_name, edit_schema = (
                    self._get_edit_schema(resource_name, resource_cfg,
                                          read_schema))
                schemas[edit_schema_name] = edit_schema
            if resource_cfg.get('searchable', True):
                filter_schemas = (
                    self._get_filter_schemas(resource_name, resource_cfg,
                                           read_schema))
                for filter_schema_name, filter_schema in filter_schemas:
                    schemas[filter_schema_name] = filter_schema
                query_schema_name, query_schema = (
                    self._get_query_schema(resource_name, resource_cfg,
                                           read_schema))
                schemas[query_schema_name] = query_schema

                search_schema_name, search_schema = (
                    self._get_search_schema(resource_name, resource_cfg,
                                            read_schema))
                schemas[search_schema_name] = search_schema
                new_search_schema_name, new_search_schema = (
                    self._get_new_search_schema(resource_name, resource_cfg,
                                                read_schema))
                schemas[new_search_schema_name] = new_search_schema
        return schemas

    def _get_paginator_schema(self):
        return OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('count', {'type': 'integer'}),
                ('page', {'type': 'integer', 'default': 1, 'minimum': 1}),
                ('items_per_page', {'type': 'integer', 'default': 10, 'minimum': 1}),
            ])),
            ('required', ['page', 'items_per_page']),
        ])

    def _get_paginated_subset_schema(self, resource_name, resource_cfg,
                                     read_schema):
        paginated_schema_name = self._get_paginated_schema_name(resource_name)
        paginated_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('paginator', {'$ref': self._get_paginator_schema_path()}),
                ('items', OrderedDict([
                    ('type', 'array'),
                    ('items',
                        {'$ref':
                         self._get_read_schema_path(resource_name)}),
                ])),
            ])),
            ('required', ['paginator', 'items']),
        ])
        return paginated_schema_name, paginated_schema

    def _get_edit_schema(self, resource_name, resource_cfg, read_schema):
        edit_schema_name = self._get_edit_schema_name(resource_name)
        edit_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('data', {
                    '$ref':
                    self._get_new_schema_path(resource_name)}),
                ('resource', {
                    '$ref':
                    self._get_read_schema_path(resource_name)}),
            ])),
            ('required', ['data', 'resource']),
        ])
        return edit_schema_name, edit_schema

    def _get_filter_schemas(self, resource_name, resource_cfg, read_schema):
        """Each resource will generate multiple filter schemas: a coordinative
        one, a negative one, a simple one and zero or more related (relational)
        ones, depending on how many other resources (models) it is related to.
        This method returns these schemas as a list.

        Note, there is a shorthand filter schema, which is based on arrays and
        which is exemplified via the following (and which canNOT be described
        using the OpenAPI spec)::

            ["and", [["Location", "purpose", "=", "AS"],
                     ["Location", "description", "regex", "2018"]]]
            ["not", ["Location", "purpose", "=", "AS"]]
            ["Location", "purpose", "=", "AS"]
            ["Location", "space", "path", "like", "/usr/data/%"]

        Then there is the long-hand filter schema, which is based on objects
        and which is exemplified via the following (which CAN be described
        using the OpenAPI spec)::

            {"conjunction": "and",
             "complement": [
                {"attribute": "purpose",
                 "relation": "=",
                 "value": "AS"},
                {"attribute": "description",
                 "relation": "regex",
                 "value": "2018"}]}

            {"negation": "not",
             "complement": {"attribute": "purpose",
                            "relation": "=",
                            "value": "AS"}}

            {"attribute": "purpose", "relation": "=", "value": "AS"}

            {"attribute": "space",
             "subattribute": "path",
             "relation": "like",
             "value": "/usr/data/%"}

        Note that the filter schema is inherently recursive and the Swagger-ui
        web app cannot currently fully display a recursive schema. See
        https://github.com/swagger-api/swagger-ui/issues/1679.
        """
        return (
            [self._get_simple_filter_schema(resource_name, resource_cfg)] +
            self._get_related_filter_schemas(resource_name, resource_cfg) +
            [self._get_coordinative_filter_schema(resource_name, resource_cfg),
             self._get_negative_filter_schema(resource_name, resource_cfg),
             self._get_array_filter_schema(resource_name, resource_cfg),
             self._get_object_filter_schema(resource_name, resource_cfg),
             self._get_filter_schema(resource_name, resource_cfg)])

    def _get_simple_filter_schema(self, resource_name, resource_cfg):
        model_cls_name = resource_cfg['resource_cls'].model_cls.__name__
        simple_schema_name = self._get_simple_filter_schema_name(resource_name)
        simple_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('attribute', OrderedDict([
                    ('type', 'string'),
                    ('enum', self._get_simple_attributes(
                        model_cls_name, resource_cfg)),
                ])),
                ('relation', OrderedDict([
                    ('type', 'string'),
                    ('enum', self._get_relations(resource_name, resource_cfg)),
                ])),
                ('value', {'anyOf': [{'type': 'string'},
                                     {'type': 'number'},
                                     {'type': 'boolean'}]}),
            ])),
        ])
        return simple_schema_name, simple_schema

    def _get_query_schemata(self, resource_cfg):
        resource_cls = resource_cfg['resource_cls']
        query_builder = resource_cls._get_query_builder()
        return query_builder.schemata

    def _get_relational_attributes(self, resource_name, resource_cfg):
        model_name = resource_cfg['resource_cls'].model_cls.__name__
        query_schemata = self._get_query_schemata(resource_cfg)
        return [(attr, cfg.get('foreign_model'))
                for attr, cfg in
                query_schemata[model_name].items()
                if cfg.get('foreign_model')]

    def _get_simple_attributes(self, model_cls_name, resource_cfg):
        query_schemata = self._get_query_schemata(resource_cfg)
        return [attr for attr, cfg in
                query_schemata[model_cls_name].items()
                if not cfg.get('foreign_model')]

    def _get_related_attributes(self, resource_cfg, related_model):
        query_schemata = self._get_query_schemata(resource_cfg)
        return [attr for attr, cfg in query_schemata[related_model].items()
                if not cfg.get('foreign_model')]

    def _get_relations(self, resource_name, resource_cfg):
        resource_cls = resource_cfg['resource_cls']
        query_builder = resource_cls._get_query_builder()
        return list(query_builder.relations)

    def _get_related_filter_schemas(self, resource_name, resource_cfg):
        schemas = []
        for attribute, related_model_cls in self._get_relational_attributes(
                resource_name, resource_cfg):
            related_schema_name = self._get_related_filter_schema_name(
                resource_name, attribute)
            related_schema = OrderedDict([
                ('type', 'object'),
                ('properties', OrderedDict([
                    ('attribute', OrderedDict([
                        ('type', 'string'),
                        ('enum', [attribute]),
                    ])),
                    ('subattribute', OrderedDict([
                        ('type', 'string'),
                        ('enum', self._get_related_attributes(
                            resource_cfg, related_model_cls)),
                    ])),
                    ('relation', OrderedDict([
                        ('type', 'string'),
                        ('enum', self._get_relations(resource_name, resource_cfg)),
                    ])),
                    ('value', {'anyOf': [{'type': 'string'},
                                         {'type': 'number'},
                                         {'type': 'boolean'}]}),
                ])),
            ])
            schemas.append((related_schema_name, related_schema))
        return schemas

    def _get_coordinative_filter_schema(self, resource_name, resource_cfg):
        coord_schema_name = self._get_coordinative_filter_schema_name(resource_name)
        coord_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('conjunction', OrderedDict([
                    ('type', 'string'),
                    ('enum', ['and', 'or']),
                ])),
                ('complement', OrderedDict([
                    ('type', 'array'),
                    ('items', {'$ref':
                               self._get_filter_schema_path(resource_name)}),
                ])),
            ])),
        ])
        return coord_schema_name, coord_schema

    def _get_negative_filter_schema(self, resource_name, resource_cfg):
        neg_schema_name = self._get_negative_filter_schema_name(resource_name)
        neg_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('negation', OrderedDict([
                    ('type', 'string'),
                    ('enum', ['not']),
                ])),
                ('complement',
                    {'$ref': self._get_filter_schema_path(resource_name)}),
            ])),
        ])
        return neg_schema_name, neg_schema

    def _get_filter_schema(self, resource_name, resource_cfg):
        filter_schema_name = self._get_filter_schema_name(resource_name)
        filter_schema = {
            'oneOf': [
                {'$ref': self._get_object_filter_schema_path(resource_name)},
                {'$ref': self._get_array_filter_schema_path(resource_name)},
            ]
        }
        return filter_schema_name, filter_schema

    def _get_array_filter_schema(self, resource_name, resource_cfg):
        array_filter_schema_name = self._get_array_filter_schema_name(resource_name)
        array_filter_schema = OrderedDict([
            ('type', 'array'),
            ('items', {'oneOf': [{'type': 'string'},
                                 {'type': 'integer'}]}),
        ])
        return array_filter_schema_name, array_filter_schema

    def _get_object_filter_schema(self, resource_name, resource_cfg):
        object_filter_schema_name = self._get_object_filter_schema_name(
            resource_name)
        object_filter_schema = {
            'oneOf': [
                {'$ref': self._get_coordinative_filter_schema_path(
                    resource_name)},
                {'$ref': self._get_negative_filter_schema_path(resource_name)},
                {'$ref': self._get_simple_filter_schema_path(resource_name)},
            ] + self._get_related_filter_schema_paths_refs(resource_name,
                                                           resource_cfg)
        }
        return object_filter_schema_name, object_filter_schema

    def _get_query_schema(self, resource_name, resource_cfg, read_schema):
        query_schema_name = self._get_query_schema_name(resource_name)
        query_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('filter', {'$ref':
                            self._get_filter_schema_path(resource_name)}),
                ('order_by', OrderedDict([
                    ('type', 'array'),
                    ('items', OrderedDict([
                        ('type', 'array'),
                        ('items', OrderedDict([
                            ('type', 'string'),
                        ])),
                    ])),
                ])),
            ])),
            ('required', ['filter']),
        ])
        return query_schema_name, query_schema

    def _get_search_schema(self, resource_name, resource_cfg, read_schema):
        search_schema_name = self._get_search_schema_name(resource_name)
        search_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('query', {'$ref': self._get_query_schema_path(resource_name)}),
                ('paginator', {'$ref': self._get_paginator_schema_path()}),
            ])),
            ('required', ['query']),
        ])
        return search_schema_name, search_schema

    def _get_new_search_schema(self, resource_name, resource_cfg, read_schema):
        new_search_schema_name = self._get_new_search_schema_name(resource_name)
        new_search_schema = OrderedDict([
            ('type', 'object'),
            ('properties', OrderedDict([
                ('search_parameters', OrderedDict([
                    # TODO: this is not a string, but an object with
                    # "attributes" and "relations".
                    ('type', 'string'),
                ])),
            ])),
            ('required', ['search_parameters']),
        ])
        return new_search_schema_name, new_search_schema

    def _get_new_schema(self, resource_name, resource_cfg, read_schema):
        new_schema_name = self._get_new_schema_name(resource_name)
        new_schema = OrderedDict([('type', 'object')])
        properties = OrderedDict()
        resource_cls = resource_cfg['resource_cls']
        resource_inst = resource_cls(
            None, server_path=self.get_dflt_server_path(),
            other_resources=self.resources)
        required_fields = []
        for field_name in resource_inst._get_new_edit_collections():
            properties[field_name] = OrderedDict([
                ('type', 'array'),
                ('items', OrderedDict([
                    ('type', 'string'),
                    ('format', 'URI of a(n) {} resource'.format(field_name)),
                ])),
            ])
            required_fields.append(field_name)
        if properties:
            new_schema['properties'] = properties
            new_schema['required'] = required_fields
        return new_schema_name, new_schema

    def _get_create_schema(self, resource_name, resource_cfg, read_schema):
        """Return a create schema for the resource named ``resource_name``.

        The create schema describes what is needed to create an instance of the
        input-named resource.
        """
        create_schema_name = self._get_create_schema_name(resource_name)
        resource_cls = resource_cfg['resource_cls']
        schema_cls = resource_cls.get_create_schema_cls()
        create_schema = self._get_create_update_schema(
            resource_name, resource_cfg, read_schema, schema_cls)
        return create_schema_name, create_schema

    def _get_update_schema(self, resource_name, resource_cfg, read_schema):
        """Return an update schema for the resource named ``resource_name``.

        The update schema describes what is needed to update an instance of the
        input-named resource.

        TODO: should every parameter in an update request be optional, given
        that the resource being updated is presumably valid?

        """
        update_schema_name = self._get_update_schema_name(resource_name)
        resource_cls = resource_cfg['resource_cls']
        schema_cls = resource_cls.get_update_schema_cls()
        update_schema = self._get_create_update_schema(
            resource_name, resource_cfg, read_schema, schema_cls)
        return update_schema_name, update_schema

    @staticmethod
    def _get_create_update_schema(resource_name, resource_cfg,
                                  read_schema, schema_cls):
        schema_properties = {}
        schema = {'type': 'object'}
        fields = schema_cls.fields
        required_fields = []
        for field_name, field in fields.items():
            field_dict = {
                ResourceURI: single_reference_mut_field_dict,
                ForEach: multi_reference_mut_field_dict,
                OneOf: enum_field_dict,
                Any: disjunctive_field_dict,
            }.get(type(field), scalar_mut_field_dict)(
                **{'field': field})
            if not field_dict.get('type') and not field_dict.get('anyOf'):
                logger.warning('{}.{} is of unknown type (class {})'.format(
                    resource_name, field_name, type(field)))
                continue
            default = read_schema['properties'].get(field_name, {}).get(
                'default', NOT_PROVIDED)
            if default != NOT_PROVIDED:
                field_dict['default'] = default
            if field_name in read_schema.get('required', []):
                required_fields.append(field_name)
            description = read_schema['properties'].get(field_name, {}).get(
                'description')
            if description:
                field_dict['description'] = description
            schema_properties[field_name] = field_dict
        schema['properties'] = schema_properties
        if required_fields:
            schema['required'] = required_fields
        return schema

    def _get_read_schema(self, resource_name, resource_cfg):
        """Return a read schema for the resource named ``resource_name``.

        The read schema describes what is returned by the server as a
        representation of an instance of the input-named resource.
        """
        read_schema_name = self._get_read_schema_name(resource_name)
        read_schema_properties = {}
        read_schema = {'type': 'object'}
        resource_cls = resource_cfg['resource_cls']
        model_cls = resource_cls.model_cls
        fields = model_cls._meta.get_fields()
        required_fields = []
        for field in fields:
            field_name = field.name
            field_name, field_dict = {
                ForeignKey: single_reference_field_dict,
                OneToOneRel: single_reference_field_dict,
                ManyToManyField: multi_reference_field_dict,
                ManyToManyRel: multi_reference_field_dict,
                ManyToOneRel: multi_reference_field_dict,
            }.get(type(field), scalar_field_dict)(
                field_name=field_name, field=field)
            choices = get_choices(field)
            if choices:
                field_dict['enum'] = choices
            if getattr(field, 'null', False) is True:
                field_dict['nullable'] = True
            default = get_default(field)
            required, field_is_null = get_required(field, default)
            default = get_default_for_type(field, default, field_is_null)
            if default != NOT_PROVIDED:
                field_dict['default'] = default
            if required:
                required_fields.append(field_name)
            if not field_dict.get('type'):
                logger.warning('{}.{} is of unknown type (class {})'.format(
                    resource_name, field.name, type(field)))
                continue
            description = getattr(field, 'help_text', None)
            if description:
                if callable(description):
                    description = description()
                field_dict['description'] = str(description)
            read_schema_properties[field_name] = field_dict
        read_schema['properties'] = read_schema_properties
        if required_fields:
            read_schema['required'] = required_fields
        return read_schema_name, read_schema

    def get_api_version_slug(self):
        try:
            return self._get_api_version_slug(self.api_version)
        except ValueError:
            return self.api_version

    @staticmethod
    def _get_api_version_slug(version):
        """Given a version number like 'X.Y.Z', return a slug representation of
        it. E.g.,

            >>> get_api_version_slug('3.0.0')
            ... 'v3'
            >>> get_api_version_slug('3.0.1')
            ... 'v3_0_1'
            >>> get_api_version_slug('3.0')
            ... 'v3'
            >>> get_api_version_slug('3.9')
            ... 'v3_9'
        """
        parts = version.strip().split('.')
        new_parts = []
        for index, part in enumerate(parts):
            part_int = int(part)
            if part_int:
                new_parts.append(part)
            else:
                parts_to_right = parts[index + 1:]
                non_empty_ptr = [p for p in parts_to_right if int(p)]
                if non_empty_ptr:
                    new_parts.append(part)
        return 'v{}'.format('_'.join(new_parts))


def single_reference_field_dict(**kwargs):
    """Return an OpenAPI OrderedDict for a Django ForeingKey or OneToOneRel.
    """
    if isinstance(kwargs['field'], OneToOneRel):
        return (kwargs['field'].get_accessor_name(),
                OrderedDict([('type', 'string'), ('format', 'uri')]))
    return (kwargs['field_name'],
            OrderedDict([('type', 'string'), ('format', 'uri')]))


def multi_reference_field_dict(**kwargs):
    """Return an OpenAPI OrderedDict for a Django ManyToManyField,
    ManyToManyRel, or ManyToOneRel.
    """
    field_name = kwargs.get('field_name')
    if isinstance(kwargs['field'], ManyToOneRel):
        field_name = kwargs['field'].get_accessor_name()
    return field_name, OrderedDict([
        ('type', 'array'),
        ('items', OrderedDict([
            ('type', 'string'), ('format', 'uri')]))])


def scalar_field_dict(**kwargs):
    """Return an OpenAPI OrderedDict for a Django scalar field, e.g., a string
    or an int.
    """
    field = kwargs.get('field')
    openapi_type = django_field2openapi_type.get(
        type(field))
    field_dict = OrderedDict([('type', openapi_type)])
    openapi_format = django_field2openapi_format.get(
        type(field))
    if openapi_format:
        field_dict['format'] = openapi_format
    return kwargs['field_name'], field_dict


def get_choices(field):
    choices = getattr(field, 'choices', None)
    if choices:
        return [c[0] for c in choices]
    return None


def get_default(field):
    return getattr(field, 'default', NOT_PROVIDED)


def get_required(field, default):
    field_is_null = getattr(field, 'null', False)
    if isinstance(field, (OneToOneRel, ManyToManyRel, ManyToOneRel)):
        return False, field_is_null
    field_is_blank = getattr(field, 'blank', False)
    if (not field_is_blank) and (default == NOT_PROVIDED):
        return True, field_is_null
    return False, field_is_null


def _get_format_from_resource_uri_validator(resource_uri_validator):
    resource_name = resource_uri_validator.model_cls.__name__.lower()
    return 'URI of a {} resource'.format(resource_name)


def single_reference_mut_field_dict(**kwargs):
    format_ = _get_format_from_resource_uri_validator(kwargs['field'])
    return OrderedDict([('type', 'string'),
                        ('format', format_)])


def multi_reference_mut_field_dict(**kwargs):
    format_ = _get_format_from_resource_uri_validator(
        kwargs['field'].validators[0])
    return OrderedDict([
        ('type', 'array'),
        ('items', OrderedDict([
            ('type', 'string'),
            ('format', format_),
        ])),
    ])


def enum_field_dict(**kwargs):
    enum = list(kwargs['field'].list)
    enum_type = type(enum[0])
    return OrderedDict([
        ('type', python_type2openapi_type.get(enum_type, 'string')),
        ('enum', enum)])


def disjunctive_field_dict(**kwargs):
    anyOf = []
    field_dict = OrderedDict([('anyOf', anyOf)])
    for validator in kwargs['field'].validators:
        validator_dict = OrderedDict()
        validator_dict['type'] = formencode_field2openapi_type.get(
            type(validator), 'string')
        validator_format = (
            formencode_field2openapi_format.get(
                type(validator)))
        if validator_format:
            validator_dict['format'] = validator_format
        anyOf.append(validator_dict)
    return field_dict


def scalar_mut_field_dict(**kwargs):
    openapi_type = formencode_field2openapi_type.get(
        type(kwargs['field']))
    field_dict = OrderedDict([('type', openapi_type)])
    openapi_format = formencode_field2openapi_format.get(
        type(kwargs['field']))
    if openapi_format:
        field_dict['format'] = openapi_format
    field = kwargs['field']
    field_min = getattr(field, 'min', None)
    field_max = getattr(field, 'max', None)
    if field_min:
        field_dict['minLength'] = field_min
    if field_max:
        field_dict['maxLength'] = field_max
    return field_dict


def get_collection_targeting_openapi_path(rsrc_collection_name,
                                          modifiers=None):
    """Return an OpenAPI path of the form '/<rsrc_collection_name>/'
    with optional trailing modifiers, e.g., '/<rsrc_collection_name>/new/'.
    """
    if modifiers:
        return r'/{rsrc_collection_name}/{modifiers}/'.format(
            rsrc_collection_name=rsrc_collection_name,
            modifiers='/'.join(modifiers))
    return r'/{rsrc_collection_name}/'.format(
        rsrc_collection_name=rsrc_collection_name)


def get_member_targeting_openapi_path(resource_name, rsrc_collection_name,
                                      pk_patt, resource_cls, modifiers=None):
    """Return a regex of the form '^<rsrc_collection_name>/<pk>/$'
    with optional modifiers after the pk, e.g.,
    '^<rsrc_collection_name>/<pk>/edit/$'.
    """
    pk_type = 'string'
    pk_format = 'uuid'
    primary_key = getattr(resource_cls, 'primary_key', 'uuid')
    if primary_key == 'id':
        pk_type = 'integer'
        pk_format = 'database id'
    path_params = [OrderedDict([
        ('in', 'path'),
        ('name', 'pk'),
        ('required', True),
        ('schema', OrderedDict([
            ('type', pk_type),
            ('format', pk_format),
        ])),
        ('description', 'The primary key of the {}.'.format(resource_name)),
    ])]
    if modifiers:
        path = (r'/{rsrc_collection_name}/{{pk}}/'
                r'{modifiers}/'.format(
                    rsrc_collection_name=rsrc_collection_name,
                    pk_patt=pk_patt,
                    modifiers='/'.join(modifiers)))
    else:
        path = r'/{rsrc_collection_name}/{{pk}}/'.format(
            rsrc_collection_name=rsrc_collection_name, pk_patt=pk_patt)
    return path, path_params


def _summarize(action, resource_name, rsrc_collection_name):
    create_summary = 'Create a new {}.'.format(resource_name)
    delete_summary = 'Delete an existing {}.'.format(resource_name)
    edit_summary = 'Get the data needed to update an existing {}.'.format(
        resource_name)
    index_summary = 'View all {}.'.format(rsrc_collection_name)
    new_summary = 'Get the data needed to create a new {}.'.format(
        resource_name)
    show_summary = 'View an existing {}.'.format(resource_name)
    update_summary = 'Update an existing {}.'.format(resource_name)
    search_summary = 'Search over all {}.'.format(rsrc_collection_name)
    search_post_summary = search_summary
    new_search_summary = 'Get the data needed to search over all {}.'.format(
        rsrc_collection_name)
    return {
        'create': (create_summary, create_summary),
        'delete': (delete_summary, delete_summary),
        'edit': (edit_summary, edit_summary),
        'index': (index_summary, index_summary),
        'new': (new_summary, new_summary),
        'show': (show_summary, show_summary),
        'update': (update_summary, update_summary),
        'search': (search_summary, search_summary),
        'search_post': (search_post_summary, search_post_summary),
        'new_search': (new_search_summary, new_search_summary),
    }[action]


def schema_name2path(schema_name):
    return '{}{}'.format(SCHEMAS_ABS_PATH, schema_name)


def get_error_schema_path():
    return schema_name2path(ERROR_SCHEMA_NAME)


def get_ref_response(description, ref, examples=None):
    """Given a description string and a ref(erence) path to an existing
    schema, return the dict describing that response.
    """
    application_json = OrderedDict([
        ('schema', OrderedDict([
            ('$ref', ref),
        ])),
    ])
    if examples:
        application_json['examples'] = examples
    return OrderedDict([
        ('description', description),
        ('content', OrderedDict([
            ('application/json', application_json),
        ])),
    ])


def _get_operation_id(action, resource_name):
    operation_name = {
        'index': 'get_many',
        'show': 'get',
        'new': 'data_for_new',
        'edit': 'data_for_edit',
        'search_post': 'search',
    }.get(action, action)
    return '{}.{}'.format(operation_name, resource_name)


def get_default_for_type(field, default, field_is_null):
    if field_is_null:
        return None
    return {
        'integer': 0,
        'float': 0.0,
        'boolean': False,
    }.get(django_field2openapi_type.get(type(field), 'string'), '')
