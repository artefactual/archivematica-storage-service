"""Remple OpenAPI Client

This module is not a code generator. It does not generate source code. It takes
an OpenAPI 3.0 definition of an API as an OrderedDict (see OPENAPI_SPEC) and
returns a module with a class (dynamically named according to the title of the
API defined in the OpenAPI spec) that provides a Pythonic interface to the
OpenAPI-described API.

Imagine an API entitled "Archivematica Storage Service API" and which exposes
CRUD endpoints on two resources: locations and spaces. Example usage might be::

    >>> from clientbuilder import ArchivematicaStorageServiceApiClient
    >>> c = ArchivematicaStorageServiceApiClient(
    ...     username='test',
    ...     api_key='test',
    ...     url='http://127.0.0.1:62081/')
    >>> first_2_spaces = c.space.get_many(
    ...     items_per_page=2, order_by_attribute='id', page=1)['items']
    >>> first_space = first_2_spaces[0]
    >>> locations_of_first_space = c.location.search({
    ...     'filter': ['space', 'uuid', '=', first_space['uuid']]})[
    ...     'items']
    >>> first_location = c.location.get(locations_of_first_space[0]['uuid'])
    >>> first_location['purpose'] = 'AS'
    >>> updated_first_location = c.location.update(
    ...     pk=first_location['uuid'], **first_location)
    >>> new_location = c.location.create(
    ...     purpose='AS',
    ...     relative_path='some/path',
    ...     space=first_space['uuid'])
    >>> pprint.pprint(new_location)
    ... {u'pipeline': [u'bb603958-c7f6-46c0-8677-7ce1a4a45497'],
    ...  u'used': 0,
    ...  u'description': None,
    ...  u'space': u'ad48b0df-295e-4f97-810e-b8de14b92c4b',
    ...  u'enabled': True,
    ...  u'quota': None,
    ...  u'relative_path': u'some/path',
    ...  u'purpose': u'AS',
    ...  u'id': 6,
    ...  u'resource_uri': u'/api/v3/locations/ec9c2e51-8883-472a-986a-48c7dc44e3a9/',
    ...  u'replicators': [],
    ...  u'uuid': u'ec9c2e51-8883-472a-986a-48c7dc44e3a9'}

TODOs:

- handle client-side validation of circular request bodies, i.e., search
- Document that `update` (PUT) is update and not PATCH. That is, the resource
  sent with an update/PUT request determines the updated state of the new
  resource completely. You cannot send just the updated attributes. You must
  send all attributes. That is, you must do your "patching" on the client and
  send the *entire* new state of the updated resource to the server.

"""


from collections import OrderedDict
import logging
import json
import pprint
import sys
import textwrap
import urllib3

import requests


logger = logging.getLogger(__name__)
log_lvl = logging.INFO
out_hdlr = logging.StreamHandler(sys.stdout)
logger.addHandler(out_hdlr)
logger.setLevel(log_lvl)




OPENAPI_SPEC = (
OrderedDict([('openapi', '3.0.0'), ('info', OrderedDict([('version', '3.0.0'), ('title', 'Archivematica Storage Service API'), ('description', 'An API for the Archivematica Storage Service.')])), ('servers', [OrderedDict([('url', '/api/v3'), ('description', 'The default server for the Archivematica Storage Service.')])]), ('security', [OrderedDict([('ApiKeyAuth', [])])]), ('components', OrderedDict([('securitySchemes', OrderedDict([('ApiKeyAuth', OrderedDict([('type', 'apiKey'), ('in', 'header'), ('name', 'Authorization')]))])), ('parameters', OrderedDict([('items_per_page', OrderedDict([('in', 'query'), ('name', 'items_per_page'), ('required', False), ('schema', OrderedDict([('type', 'integer'), ('minimum', 1), ('default', 10)])), ('description', 'The maximum number of items to return.')])), ('page', OrderedDict([('in', 'query'), ('name', 'page'), ('required', False), ('schema', OrderedDict([('type', 'integer'), ('minimum', 1), ('default', 1)])), ('description', 'The page number to return.')])), ('order_by_direction', OrderedDict([('in', 'query'), ('name', 'order_by_direction'), ('schema', OrderedDict([('type', 'string'), ('enum', ['-', 'ascending', 'asc', 'descending', 'desc'])])), ('required', False), ('description', 'The direction of the ordering; omitting this parameter means ascending direction.')])), ('order_by_attribute', OrderedDict([('in', 'query'), ('name', 'order_by_attribute'), ('schema', {'type': 'string'}), ('description', 'Attribute of the resource that view results should be ordered by.'), ('required', False)])), ('order_by_subattribute', OrderedDict([('in', 'query'), ('name', 'order_by_subattribute'), ('schema', {'type': 'string'}), ('required', False), ('description', 'Attribute of the related attribute order_by_attribute of the resource that view results should be ordered by.')]))])), ('schemas', OrderedDict([('ErrorSchema', OrderedDict([('type', 'object'), ('properties', OrderedDict([('error', OrderedDict([('type', 'string')]))])), ('required', ['error'])])), ('PaginatorSchema', OrderedDict([('type', 'object'), ('properties', OrderedDict([('count', {'type': 'integer'}), ('page', {'default': 1, 'minimum': 1, 'type': 'integer'}), ('items_per_page', {'default': 10, 'minimum': 1, 'type': 'integer'})])), ('required', ['page', 'items_per_page'])])), ('LocationView', {'required': ['space', 'purpose', 'relative_path'], 'type': 'object', 'properties': {u'masters': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'used': OrderedDict([('type', 'integer'), ('default', 0), ('description', 'Amount used, in bytes.')]), 'uuid': OrderedDict([('type', 'string'), ('format', 'uuid'), ('description', 'Unique identifier')]), 'space': OrderedDict([('type', 'string'), ('format', 'uri')]), u'locationpipeline_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'True if space can be accessed.')]), 'quota': OrderedDict([('type', 'integer'), ('nullable', True), ('default', None), ('description', 'Size, in bytes (optional)')]), 'relative_path': OrderedDict([('type', 'string'), ('description', "Path to location, relative to the storage space's path.")]), u'package_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'purpose': OrderedDict([('type', 'string'), ('enum', ['AR', 'AS', 'CP', 'DS', 'SD', 'SS', 'BL', 'TS', 'RP']), ('description', 'Purpose of the space.  Eg. AIP storage, Transfer source')]), 'replicators': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')])), ('description', 'Other locations that will be used to create replicas of the packages stored in this location')]), 'pipeline': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')])), ('description', 'UUID of the Archivematica instance using this location.')]), u'id': OrderedDict([('type', 'integer')]), 'description': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'Human-readable description.')])}}), ('PaginatedSubsetOfLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('paginator', {'$ref': '#/components/schemas/PaginatorSchema'}), ('items', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/LocationView'})]))])), ('required', ['paginator', 'items'])])), ('LocationCreate', {'required': ['space', 'relative_path', 'purpose'], 'type': 'object', 'properties': {'pipeline': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of a pipeline resource')])), ('description', 'UUID of the Archivematica instance using this location.')]), 'description': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Human-readable description.')]), 'space': OrderedDict([('type', 'string'), ('format', 'uuid of a space resource')]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'True if space can be accessed.')]), 'quota': OrderedDict([('type', 'integer'), ('default', None), ('description', 'Size, in bytes (optional)')]), 'relative_path': OrderedDict([('type', 'string'), ('description', "Path to location, relative to the storage space's path.")]), 'purpose': OrderedDict([('type', 'string'), ('enum', ['AR', 'AS', 'CP', 'DS', 'SD', 'SS', 'BL', 'TS', 'RP']), ('description', 'Purpose of the space.  Eg. AIP storage, Transfer source')]), 'replicators': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of a location resource')])), ('description', 'Other locations that will be used to create replicas of the packages stored in this location')])}}), ('LocationUpdate', {'required': ['space', 'relative_path', 'purpose'], 'type': 'object', 'properties': {'pipeline': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of a pipeline resource')])), ('description', 'UUID of the Archivematica instance using this location.')]), 'description': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Human-readable description.')]), 'space': OrderedDict([('type', 'string'), ('format', 'uuid of a space resource')]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'True if space can be accessed.')]), 'quota': OrderedDict([('type', 'integer'), ('default', None), ('description', 'Size, in bytes (optional)')]), 'relative_path': OrderedDict([('type', 'string'), ('description', "Path to location, relative to the storage space's path.")]), 'purpose': OrderedDict([('type', 'string'), ('enum', ['AR', 'AS', 'CP', 'DS', 'SD', 'SS', 'BL', 'TS', 'RP']), ('description', 'Purpose of the space.  Eg. AIP storage, Transfer source')]), 'replicators': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of a location resource')])), ('description', 'Other locations that will be used to create replicas of the packages stored in this location')])}}), ('NewLocation', OrderedDict([('type', 'object'), ('properties', OrderedDict([('spaces', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of an instance of the spaces resource')]))])), ('pipelines', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of an instance of the pipelines resource')]))])), ('locations', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uuid of an instance of the locations resource')]))]))])), ('required', ['spaces', 'pipelines', 'locations'])])), ('EditALocation', OrderedDict([('type', 'object'), ('properties', OrderedDict([('data', {'$ref': '#/components/schemas/NewLocation'}), ('resource', {'$ref': '#/components/schemas/LocationView'})])), ('required', ['data', 'resource'])])), ('SimpleFilterOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsMasters', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'masters'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsSpace', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['space'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['last_verified', 'used', 'verified', 'uuid', 'access_protocol', 'staging_path', 'size', 'path', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsLocationpipeline_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'locationpipeline_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', [u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsPackage_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'package_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsReplicators', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['replicators'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverLocationsPipeline', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['pipeline'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['api_key', 'uuid', 'enabled', 'api_username', 'remote_name', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('CoordinativeFilterOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('conjunction', OrderedDict([('type', 'string'), ('enum', ['and', 'or'])])), ('complement', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/FilterOverLocations'})]))]))])), ('NegativeFilterOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('negation', OrderedDict([('type', 'string'), ('enum', ['not'])])), ('complement', {'$ref': '#/components/schemas/FilterOverLocations'})]))])), ('ArrayFilterOverLocations', OrderedDict([('type', 'array'), ('items', {'oneOf': [{'type': 'string'}, {'type': 'integer'}]})])), ('ObjectFilterOverLocations', {'oneOf': [{'$ref': '#/components/schemas/CoordinativeFilterOverLocations'}, {'$ref': '#/components/schemas/NegativeFilterOverLocations'}, {'$ref': '#/components/schemas/SimpleFilterOverLocations'}, {'$ref': '#/components/schemas/FilterOverLocationsMasters'}, {'$ref': '#/components/schemas/FilterOverLocationsSpace'}, {'$ref': '#/components/schemas/FilterOverLocationsLocationpipeline_set'}, {'$ref': '#/components/schemas/FilterOverLocationsPackage_set'}, {'$ref': '#/components/schemas/FilterOverLocationsReplicators'}, {'$ref': '#/components/schemas/FilterOverLocationsPipeline'}]}), ('FilterOverLocations', {'oneOf': [{'$ref': '#/components/schemas/ObjectFilterOverLocations'}, {'$ref': '#/components/schemas/ArrayFilterOverLocations'}]}), ('SearchQueryOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('filter', {'$ref': '#/components/schemas/FilterOverLocations'}), ('order_by', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string')]))]))]))])), ('required', ['filter'])])), ('SearchOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('query', {'$ref': '#/components/schemas/SearchQueryOverLocations'}), ('paginator', {'$ref': '#/components/schemas/PaginatorSchema'})])), ('required', ['query'])])), ('DataForNewSearchOverLocations', OrderedDict([('type', 'object'), ('properties', OrderedDict([('search_parameters', OrderedDict([('type', 'string')]))])), ('required', ['search_parameters'])])), ('PackageView', {'required': ['current_location', 'current_path', 'package_type', 'related_packages'], 'type': 'object', 'properties': {'size': OrderedDict([('type', 'integer'), ('default', 0), ('description', 'Size in bytes of the package')]), 'status': OrderedDict([('type', 'string'), ('enum', ['PENDING', 'STAGING', 'UPLOADED', 'VERIFIED', 'FAIL', 'DEL_REQ', 'DELETED', 'FINALIZE']), ('default', 'FAIL'), ('description', 'Status of the package in the storage service.')]), 'package_type': OrderedDict([('type', 'string'), ('enum', ['AIP', 'AIC', 'SIP', 'DIP', 'transfer', 'file', 'deposit'])]), u'fixitylog_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'origin_pipeline': OrderedDict([('type', 'string'), ('format', 'uri'), ('nullable', True)]), 'uuid': OrderedDict([('type', 'string'), ('format', 'uuid'), ('description', 'Unique identifier')]), u'replicas': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), u'event_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), u'file_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'replicated_package': OrderedDict([('type', 'string'), ('format', 'uri'), ('nullable', True)]), 'misc_attributes': OrderedDict([('type', 'object'), ('nullable', True), ('default', {}), ('description', 'For storing flexible, often Space-specific, attributes')]), 'pointer_file_location': OrderedDict([('type', 'string'), ('format', 'uri'), ('nullable', True)]), 'encryption_key_fingerprint': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'The fingerprint of the GPG key used to encrypt the package, if applicable')]), u'packagedownloadtask_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'current_location': OrderedDict([('type', 'string'), ('format', 'uri')]), 'pointer_file_path': OrderedDict([('type', 'string'), ('nullable', True)]), 'related_packages': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'current_path': OrderedDict([('type', 'string')]), u'id': OrderedDict([('type', 'integer')]), 'description': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'Human-readable description.')])}}), ('PaginatedSubsetOfPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('paginator', {'$ref': '#/components/schemas/PaginatorSchema'}), ('items', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/PackageView'})]))])), ('required', ['paginator', 'items'])])), ('SimpleFilterOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesFixitylog_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'fixitylog_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['datetime_reported', 'error_details', u'id', 'success'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesOrigin_pipeline', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['origin_pipeline'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['api_key', 'uuid', 'enabled', 'api_username', 'remote_name', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesReplicas', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'replicas'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesEvent_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'event_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['status', 'user_id', 'event_type', 'store_data', 'status_time', 'status_reason', u'id', 'user_email', 'event_reason'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesFile_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'file_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['accessionid', 'origin', 'source_package', 'name', 'checksum', 'stored', 'source_id', u'id', 'uuid'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesReplicated_package', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['replicated_package'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesPointer_file_location', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['pointer_file_location'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesPackagedownloadtask_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'packagedownloadtask_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['uuid', 'download_completion_time', 'downloads_completed', u'id', 'downloads_attempted'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesCurrent_location', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['current_location'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPackagesRelated_packages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['related_packages'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('CoordinativeFilterOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('conjunction', OrderedDict([('type', 'string'), ('enum', ['and', 'or'])])), ('complement', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/FilterOverPackages'})]))]))])), ('NegativeFilterOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('negation', OrderedDict([('type', 'string'), ('enum', ['not'])])), ('complement', {'$ref': '#/components/schemas/FilterOverPackages'})]))])), ('ArrayFilterOverPackages', OrderedDict([('type', 'array'), ('items', {'oneOf': [{'type': 'string'}, {'type': 'integer'}]})])), ('ObjectFilterOverPackages', {'oneOf': [{'$ref': '#/components/schemas/CoordinativeFilterOverPackages'}, {'$ref': '#/components/schemas/NegativeFilterOverPackages'}, {'$ref': '#/components/schemas/SimpleFilterOverPackages'}, {'$ref': '#/components/schemas/FilterOverPackagesFixitylog_set'}, {'$ref': '#/components/schemas/FilterOverPackagesOrigin_pipeline'}, {'$ref': '#/components/schemas/FilterOverPackagesReplicas'}, {'$ref': '#/components/schemas/FilterOverPackagesEvent_set'}, {'$ref': '#/components/schemas/FilterOverPackagesFile_set'}, {'$ref': '#/components/schemas/FilterOverPackagesReplicated_package'}, {'$ref': '#/components/schemas/FilterOverPackagesPointer_file_location'}, {'$ref': '#/components/schemas/FilterOverPackagesPackagedownloadtask_set'}, {'$ref': '#/components/schemas/FilterOverPackagesCurrent_location'}, {'$ref': '#/components/schemas/FilterOverPackagesRelated_packages'}]}), ('FilterOverPackages', {'oneOf': [{'$ref': '#/components/schemas/ObjectFilterOverPackages'}, {'$ref': '#/components/schemas/ArrayFilterOverPackages'}]}), ('SearchQueryOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('filter', {'$ref': '#/components/schemas/FilterOverPackages'}), ('order_by', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string')]))]))]))])), ('required', ['filter'])])), ('SearchOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('query', {'$ref': '#/components/schemas/SearchQueryOverPackages'}), ('paginator', {'$ref': '#/components/schemas/PaginatorSchema'})])), ('required', ['query'])])), ('DataForNewSearchOverPackages', OrderedDict([('type', 'object'), ('properties', OrderedDict([('search_parameters', OrderedDict([('type', 'string')]))])), ('required', ['search_parameters'])])), ('PipelineView', {'required': ['uuid'], 'type': 'object', 'properties': {'api_key': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'API key to use when making API calls to the pipeline.')]), 'uuid': OrderedDict([('type', 'string'), ('format', 'uuid'), ('description', 'Identifier for the Archivematica pipeline')]), u'event_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), u'locationpipeline_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'Enabled if this pipeline is able to access the storage service.')]), u'package_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'location': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), 'api_username': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'Username to use when making API calls to the pipeline.')]), 'remote_name': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'Host or IP address of the pipeline server for making API calls.')]), u'id': OrderedDict([('type', 'integer')]), 'description': OrderedDict([('type', 'string'), ('nullable', True), ('default', None), ('description', 'Human readable description of the Archivematica instance.')])}}), ('PaginatedSubsetOfPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('paginator', {'$ref': '#/components/schemas/PaginatorSchema'}), ('items', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/PipelineView'})]))])), ('required', ['paginator', 'items'])])), ('PipelineCreate', {'type': 'object', 'properties': {'remote_name': OrderedDict([('anyOf', [OrderedDict([('type', 'string'), ('format', 'ipv4')]), OrderedDict([('type', 'string'), ('format', 'uri')])]), ('default', None), ('description', 'Host or IP address of the pipeline server for making API calls.')]), 'api_key': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'API key to use when making API calls to the pipeline.')]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'Enabled if this pipeline is able to access the storage service.')]), 'description': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Human readable description of the Archivematica instance.')]), 'api_username': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Username to use when making API calls to the pipeline.')])}}), ('PipelineUpdate', {'type': 'object', 'properties': {'remote_name': OrderedDict([('anyOf', [OrderedDict([('type', 'string'), ('format', 'ipv4')]), OrderedDict([('type', 'string'), ('format', 'uri')])]), ('default', None), ('description', 'Host or IP address of the pipeline server for making API calls.')]), 'api_key': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'API key to use when making API calls to the pipeline.')]), 'enabled': OrderedDict([('type', 'boolean'), ('default', True), ('description', 'Enabled if this pipeline is able to access the storage service.')]), 'description': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Human readable description of the Archivematica instance.')]), 'api_username': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', None), ('description', 'Username to use when making API calls to the pipeline.')])}}), ('NewPipeline', OrderedDict([('type', 'object'), ('properties', OrderedDict()), ('required', [])])), ('EditAPipeline', OrderedDict([('type', 'object'), ('properties', OrderedDict([('data', {'$ref': '#/components/schemas/NewPipeline'}), ('resource', {'$ref': '#/components/schemas/PipelineView'})])), ('required', ['data', 'resource'])])), ('SimpleFilterOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['api_key', 'uuid', 'enabled', 'api_username', 'remote_name', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPipelinesEvent_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'event_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['status', 'user_id', 'event_type', 'store_data', 'status_time', 'status_reason', u'id', 'user_email', 'event_reason'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPipelinesLocationpipeline_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'locationpipeline_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', [u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPipelinesPackage_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'package_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['size', 'status', 'package_type', 'uuid', 'misc_attributes', 'encryption_key_fingerprint', 'pointer_file_path', 'current_path', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverPipelinesLocation', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['location'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('CoordinativeFilterOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('conjunction', OrderedDict([('type', 'string'), ('enum', ['and', 'or'])])), ('complement', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/FilterOverPipelines'})]))]))])), ('NegativeFilterOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('negation', OrderedDict([('type', 'string'), ('enum', ['not'])])), ('complement', {'$ref': '#/components/schemas/FilterOverPipelines'})]))])), ('ArrayFilterOverPipelines', OrderedDict([('type', 'array'), ('items', {'oneOf': [{'type': 'string'}, {'type': 'integer'}]})])), ('ObjectFilterOverPipelines', {'oneOf': [{'$ref': '#/components/schemas/CoordinativeFilterOverPipelines'}, {'$ref': '#/components/schemas/NegativeFilterOverPipelines'}, {'$ref': '#/components/schemas/SimpleFilterOverPipelines'}, {'$ref': '#/components/schemas/FilterOverPipelinesEvent_set'}, {'$ref': '#/components/schemas/FilterOverPipelinesLocationpipeline_set'}, {'$ref': '#/components/schemas/FilterOverPipelinesPackage_set'}, {'$ref': '#/components/schemas/FilterOverPipelinesLocation'}]}), ('FilterOverPipelines', {'oneOf': [{'$ref': '#/components/schemas/ObjectFilterOverPipelines'}, {'$ref': '#/components/schemas/ArrayFilterOverPipelines'}]}), ('SearchQueryOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('filter', {'$ref': '#/components/schemas/FilterOverPipelines'}), ('order_by', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string')]))]))]))])), ('required', ['filter'])])), ('SearchOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('query', {'$ref': '#/components/schemas/SearchQueryOverPipelines'}), ('paginator', {'$ref': '#/components/schemas/PaginatorSchema'})])), ('required', ['query'])])), ('DataForNewSearchOverPipelines', OrderedDict([('type', 'object'), ('properties', OrderedDict([('search_parameters', OrderedDict([('type', 'string')]))])), ('required', ['search_parameters'])])), ('SpaceView', {'required': ['access_protocol', 'staging_path'], 'type': 'object', 'properties': {u'duracloud': OrderedDict([('type', 'string'), ('format', 'uri')]), u'lockssomatic': OrderedDict([('type', 'string'), ('format', 'uri')]), 'last_verified': OrderedDict([('type', 'string'), ('format', 'date-time'), ('nullable', True), ('default', None), ('description', 'Time this location was last verified to be accessible.')]), 'used': OrderedDict([('type', 'integer'), ('default', 0), ('description', 'Amount used in bytes')]), 'verified': OrderedDict([('type', 'boolean'), ('default', False), ('description', 'Whether or not the space has been verified to be accessible.')]), u'fedora': OrderedDict([('type', 'string'), ('format', 'uri')]), u'gpg': OrderedDict([('type', 'string'), ('format', 'uri')]), 'uuid': OrderedDict([('type', 'string'), ('format', 'uuid'), ('description', 'Unique identifier')]), 'access_protocol': OrderedDict([('type', 'string'), ('enum', ['ARKIVUM', 'DV', 'DC', 'DSPACE', 'FEDORA', 'GPG', 'FS', 'LOM', 'NFS', 'PIPE_FS', 'SWIFT']), ('description', 'How the space can be accessed.')]), 'staging_path': OrderedDict([('type', 'string'), ('description', 'Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.')]), u'dspace': OrderedDict([('type', 'string'), ('format', 'uri')]), u'nfs': OrderedDict([('type', 'string'), ('format', 'uri')]), u'arkivum': OrderedDict([('type', 'string'), ('format', 'uri')]), 'size': OrderedDict([('type', 'integer'), ('nullable', True), ('default', None), ('description', 'Size in bytes (optional)')]), u'dataverse': OrderedDict([('type', 'string'), ('format', 'uri')]), 'path': OrderedDict([('type', 'string'), ('default', ''), ('description', 'Absolute path to the space on the storage service machine.')]), u'location_set': OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string'), ('format', 'uri')]))]), u'localfilesystem': OrderedDict([('type', 'string'), ('format', 'uri')]), u'swift': OrderedDict([('type', 'string'), ('format', 'uri')]), u'id': OrderedDict([('type', 'integer')]), u'pipelinelocalfs': OrderedDict([('type', 'string'), ('format', 'uri')])}}), ('PaginatedSubsetOfSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('paginator', {'$ref': '#/components/schemas/PaginatorSchema'}), ('items', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/SpaceView'})]))])), ('required', ['paginator', 'items'])])), ('SpaceCreate', {'required': ['staging_path', 'access_protocol'], 'type': 'object', 'properties': {'path': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', ''), ('description', 'Absolute path to the space on the storage service machine.')]), 'size': OrderedDict([('type', 'integer'), ('default', None), ('description', 'Size in bytes (optional)')]), 'access_protocol': OrderedDict([('type', 'string'), ('enum', ['ARKIVUM', 'DV', 'DC', 'DSPACE', 'FEDORA', 'GPG', 'FS', 'LOM', 'NFS', 'PIPE_FS', 'SWIFT']), ('description', 'How the space can be accessed.')]), 'staging_path': OrderedDict([('type', 'string'), ('maxLength', 256), ('description', 'Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.')])}}), ('SpaceUpdate', {'required': ['staging_path'], 'type': 'object', 'properties': {'path': OrderedDict([('type', 'string'), ('maxLength', 256), ('default', ''), ('description', 'Absolute path to the space on the storage service machine.')]), 'staging_path': OrderedDict([('type', 'string'), ('maxLength', 256), ('description', 'Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.')]), 'size': OrderedDict([('type', 'integer'), ('default', None), ('description', 'Size in bytes (optional)')])}}), ('NewSpace', OrderedDict([('type', 'object'), ('properties', OrderedDict()), ('required', [])])), ('EditASpace', OrderedDict([('type', 'object'), ('properties', OrderedDict([('data', {'$ref': '#/components/schemas/NewSpace'}), ('resource', {'$ref': '#/components/schemas/SpaceView'})])), ('required', ['data', 'resource'])])), ('SimpleFilterOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', ['last_verified', 'used', 'verified', 'uuid', 'access_protocol', 'staging_path', 'size', 'path', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesDuracloud', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'duracloud'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['duraspace', 'space', 'host', 'user', 'password', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesLockssomatic', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'lockssomatic'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['collection_iri', 'external_domain', 'space', 'content_provider_id', 'sd_iri', u'id', 'checksum_type', 'au_size', 'keep_local'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesFedora', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'fedora'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['fedora_name', 'fedora_password', 'fedora_user', u'id', 'space'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesGpg', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'gpg'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', [u'id', 'key', 'space'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesDspace', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'dspace'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['space', 'sd_iri', 'metadata_policy', 'user', 'archive_format', 'password', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesNfs', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'nfs'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['manually_mounted', 'space', 'remote_path', 'version', 'remote_name', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesArkivum', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'arkivum'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['host', 'remote_user', 'remote_name', u'id', 'space'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesDataverse', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'dataverse'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['agent_name', 'agent_identifier', 'space', 'host', 'agent_type', 'api_key', u'id'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesLocation_set', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'location_set'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['used', 'uuid', 'enabled', 'quota', 'relative_path', 'purpose', u'id', 'description'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesLocalfilesystem', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'localfilesystem'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', [u'id', 'space'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesSwift', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'swift'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['username', 'container', 'space', 'region', 'auth_version', 'auth_url', 'password', u'id', 'tenant'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('FilterOverSpacesPipelinelocalfs', OrderedDict([('type', 'object'), ('properties', OrderedDict([('attribute', OrderedDict([('type', 'string'), ('enum', [u'pipelinelocalfs'])])), ('subattribute', OrderedDict([('type', 'string'), ('enum', ['remote_user', 'space', 'assume_rsync_daemon', 'remote_name', u'id', 'rsync_password'])])), ('relation', OrderedDict([('type', 'string'), ('enum', ['regex', 'gt', 'like', '!=', '=', 'contains', 'ne', '<=', 'lt', '>=', 'lte', 'in', 'regexp', 'exact', '<', 'gte', '>'])])), ('value', {'anyOf': [{'type': 'string'}, {'type': 'number'}, {'type': 'boolean'}]})]))])), ('CoordinativeFilterOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('conjunction', OrderedDict([('type', 'string'), ('enum', ['and', 'or'])])), ('complement', OrderedDict([('type', 'array'), ('items', {'$ref': '#/components/schemas/FilterOverSpaces'})]))]))])), ('NegativeFilterOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('negation', OrderedDict([('type', 'string'), ('enum', ['not'])])), ('complement', {'$ref': '#/components/schemas/FilterOverSpaces'})]))])), ('ArrayFilterOverSpaces', OrderedDict([('type', 'array'), ('items', {'oneOf': [{'type': 'string'}, {'type': 'integer'}]})])), ('ObjectFilterOverSpaces', {'oneOf': [{'$ref': '#/components/schemas/CoordinativeFilterOverSpaces'}, {'$ref': '#/components/schemas/NegativeFilterOverSpaces'}, {'$ref': '#/components/schemas/SimpleFilterOverSpaces'}, {'$ref': '#/components/schemas/FilterOverSpacesDuracloud'}, {'$ref': '#/components/schemas/FilterOverSpacesLockssomatic'}, {'$ref': '#/components/schemas/FilterOverSpacesFedora'}, {'$ref': '#/components/schemas/FilterOverSpacesGpg'}, {'$ref': '#/components/schemas/FilterOverSpacesDspace'}, {'$ref': '#/components/schemas/FilterOverSpacesNfs'}, {'$ref': '#/components/schemas/FilterOverSpacesArkivum'}, {'$ref': '#/components/schemas/FilterOverSpacesDataverse'}, {'$ref': '#/components/schemas/FilterOverSpacesLocation_set'}, {'$ref': '#/components/schemas/FilterOverSpacesLocalfilesystem'}, {'$ref': '#/components/schemas/FilterOverSpacesSwift'}, {'$ref': '#/components/schemas/FilterOverSpacesPipelinelocalfs'}]}), ('FilterOverSpaces', {'oneOf': [{'$ref': '#/components/schemas/ObjectFilterOverSpaces'}, {'$ref': '#/components/schemas/ArrayFilterOverSpaces'}]}), ('SearchQueryOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('filter', {'$ref': '#/components/schemas/FilterOverSpaces'}), ('order_by', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'array'), ('items', OrderedDict([('type', 'string')]))]))]))])), ('required', ['filter'])])), ('SearchOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('query', {'$ref': '#/components/schemas/SearchQueryOverSpaces'}), ('paginator', {'$ref': '#/components/schemas/PaginatorSchema'})])), ('required', ['query'])])), ('DataForNewSearchOverSpaces', OrderedDict([('type', 'object'), ('properties', OrderedDict([('search_parameters', OrderedDict([('type', 'string')]))])), ('required', ['search_parameters'])]))]))])), ('paths', {'/packages/new_search/': {'get': OrderedDict([('summary', 'Get the data needed to search over all packages.'), ('description', 'Get the data needed to search over all packages.'), ('operationId', 'new_search.package'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request to get the data needed to search across all packages succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/DataForNewSearchOverPackages')]))]))]))]))])), ('tags', ['packages'])])}, '/locations/new/': {'get': OrderedDict([('summary', 'Get the data needed to create a new location.'), ('description', 'Get the data needed to create a new location.'), ('operationId', 'data_for_new.location'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to create a new location resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/NewLocation')]))]))]))]))])), ('tags', ['locations'])])}, '/pipelines/{pk}/': {'put': OrderedDict([('summary', 'Update an existing pipeline.'), ('description', 'Update an existing pipeline.'), ('operationId', 'update.pipeline'), ('requestBody', OrderedDict([('description', 'JSON object required to update an existing pipeline'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/PipelineUpdate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Updating of an existing pipeline resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditAPipeline')]))]))]))])), ('404', OrderedDict([('description', 'Updating of an existing pipeline resource failed because there is no pipeline with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Updating of an existing pipeline resource failed because the user is forbidden from updating this pipeline resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('400', OrderedDict([('description', 'Updating of an existing pipeline resource failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])]), 'get': OrderedDict([('summary', 'View an existing pipeline.'), ('description', 'View an existing pipeline.'), ('operationId', 'get.pipeline'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a single pipeline succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PipelineView')]))]))]))])), ('404', OrderedDict([('description', 'Request for a single pipeline failed because there is no pipeline resource with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for a single pipeline failed because the user is forbidden from viewing this pipeline resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])]), 'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the pipeline.')])], 'delete': OrderedDict([('summary', 'Delete an existing pipeline.'), ('description', 'Delete an existing pipeline.'), ('operationId', 'delete.pipeline'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Deletion of the pipeline resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PipelineView')]))]))]))])), ('404', OrderedDict([('description', 'Deletion of the pipeline resource failed because there is no pipeline with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Deletion of the pipeline resource failed because user is forbidden from performing this action'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])])}, '/spaces/new/': {'get': OrderedDict([('summary', 'Get the data needed to create a new space.'), ('description', 'Get the data needed to create a new space.'), ('operationId', 'data_for_new.space'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to create a new space resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/NewSpace')]))]))]))]))])), ('tags', ['spaces'])])}, '/spaces/': {'post': OrderedDict([('summary', 'Create a new space.'), ('description', 'Create a new space.'), ('operationId', 'create.space'), ('requestBody', OrderedDict([('description', 'JSON object required to create a new space'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/SpaceCreate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Creation of a new space succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/SpaceView')]))]))]))])), ('400', OrderedDict([('description', 'Creation of a new space failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])]), 'search': OrderedDict([('summary', 'Search over all spaces.'), ('description', 'Search over all spaces.'), ('operationId', 'search.space'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all spaces'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverSpaces'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all spaces succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfSpaces')]))]))]))])), ('400', OrderedDict([('description', 'Search across all spaces failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])]), 'get': OrderedDict([('summary', 'View all spaces.'), ('description', 'View all spaces.'), ('operationId', 'get_many.space'), ('parameters', [{'$ref': '#/components/parameters/items_per_page'}, {'$ref': '#/components/parameters/page'}, {'$ref': '#/components/parameters/order_by_attribute'}, {'$ref': '#/components/parameters/order_by_subattribute'}, {'$ref': '#/components/parameters/order_by_direction'}]), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a collection of spaces succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfSpaces')]))]))]))])), ('400', OrderedDict([('description', 'Request for a collection of spaces failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])])}, '/pipelines/search/': {'post': OrderedDict([('summary', 'Search over all pipelines.'), ('description', 'Search over all pipelines.'), ('operationId', 'search.pipeline'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all pipelines'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverPipelines'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all pipelines succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPipelines')]))]))]))])), ('400', OrderedDict([('description', 'Search across all pipelines failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])])}, '/locations/{pk}/edit/': {'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the location.')])], 'get': OrderedDict([('summary', 'Get the data needed to update an existing location.'), ('description', 'Get the data needed to update an existing location.'), ('operationId', 'data_for_edit.location'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to edit a(n) location resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditALocation')]))]))]))])), ('404', OrderedDict([('description', 'Request for the data needed to edit a(n) location failed because there is no location resource with the specified pk'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for the data needed to edit a(n) location failed because the user is forbidden from editing this location resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])])}, '/spaces/{pk}/edit/': {'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the space.')])], 'get': OrderedDict([('summary', 'Get the data needed to update an existing space.'), ('description', 'Get the data needed to update an existing space.'), ('operationId', 'data_for_edit.space'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to edit a(n) space resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditASpace')]))]))]))])), ('404', OrderedDict([('description', 'Request for the data needed to edit a(n) space failed because there is no space resource with the specified pk'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for the data needed to edit a(n) space failed because the user is forbidden from editing this space resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])])}, '/pipelines/{pk}/edit/': {'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the pipeline.')])], 'get': OrderedDict([('summary', 'Get the data needed to update an existing pipeline.'), ('description', 'Get the data needed to update an existing pipeline.'), ('operationId', 'data_for_edit.pipeline'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to edit a(n) pipeline resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditAPipeline')]))]))]))])), ('404', OrderedDict([('description', 'Request for the data needed to edit a(n) pipeline failed because there is no pipeline resource with the specified pk'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for the data needed to edit a(n) pipeline failed because the user is forbidden from editing this pipeline resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])])}, '/spaces/{pk}/': {'put': OrderedDict([('summary', 'Update an existing space.'), ('description', 'Update an existing space.'), ('operationId', 'update.space'), ('requestBody', OrderedDict([('description', 'JSON object required to update an existing space'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/SpaceUpdate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Updating of an existing space resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditASpace')]))]))]))])), ('404', OrderedDict([('description', 'Updating of an existing space resource failed because there is no space with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Updating of an existing space resource failed because the user is forbidden from updating this space resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('400', OrderedDict([('description', 'Updating of an existing space resource failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])]), 'get': OrderedDict([('summary', 'View an existing space.'), ('description', 'View an existing space.'), ('operationId', 'get.space'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a single space succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/SpaceView')]))]))]))])), ('404', OrderedDict([('description', 'Request for a single space failed because there is no space resource with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for a single space failed because the user is forbidden from viewing this space resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])]), 'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the space.')])], 'delete': OrderedDict([('summary', 'Delete an existing space.'), ('description', 'Delete an existing space.'), ('operationId', 'delete.space'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Deletion of the space resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/SpaceView')]))]))]))])), ('404', OrderedDict([('description', 'Deletion of the space resource failed because there is no space with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Deletion of the space resource failed because user is forbidden from performing this action'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])])}, '/locations/': {'post': OrderedDict([('summary', 'Create a new location.'), ('description', 'Create a new location.'), ('operationId', 'create.location'), ('requestBody', OrderedDict([('description', 'JSON object required to create a new location'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/LocationCreate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Creation of a new location succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/LocationView')]))]))]))])), ('400', OrderedDict([('description', 'Creation of a new location failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])]), 'search': OrderedDict([('summary', 'Search over all locations.'), ('description', 'Search over all locations.'), ('operationId', 'search.location'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all locations'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverLocations'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all locations succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfLocations')]))]))]))])), ('400', OrderedDict([('description', 'Search across all locations failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])]), 'get': OrderedDict([('summary', 'View all locations.'), ('description', 'View all locations.'), ('operationId', 'get_many.location'), ('parameters', [{'$ref': '#/components/parameters/items_per_page'}, {'$ref': '#/components/parameters/page'}, {'$ref': '#/components/parameters/order_by_attribute'}, {'$ref': '#/components/parameters/order_by_subattribute'}, {'$ref': '#/components/parameters/order_by_direction'}]), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a collection of locations succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfLocations')]))]))]))])), ('400', OrderedDict([('description', 'Request for a collection of locations failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])])}, '/locations/search/': {'post': OrderedDict([('summary', 'Search over all locations.'), ('description', 'Search over all locations.'), ('operationId', 'search.location'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all locations'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverLocations'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all locations succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfLocations')]))]))]))])), ('400', OrderedDict([('description', 'Search across all locations failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])])}, '/pipelines/new_search/': {'get': OrderedDict([('summary', 'Get the data needed to search over all pipelines.'), ('description', 'Get the data needed to search over all pipelines.'), ('operationId', 'new_search.pipeline'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request to get the data needed to search across all pipelines succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/DataForNewSearchOverPipelines')]))]))]))]))])), ('tags', ['pipelines'])])}, '/spaces/new_search/': {'get': OrderedDict([('summary', 'Get the data needed to search over all spaces.'), ('description', 'Get the data needed to search over all spaces.'), ('operationId', 'new_search.space'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request to get the data needed to search across all spaces succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/DataForNewSearchOverSpaces')]))]))]))]))])), ('tags', ['spaces'])])}, '/spaces/search/': {'post': OrderedDict([('summary', 'Search over all spaces.'), ('description', 'Search over all spaces.'), ('operationId', 'search.space'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all spaces'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverSpaces'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all spaces succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfSpaces')]))]))]))])), ('400', OrderedDict([('description', 'Search across all spaces failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['spaces'])])}, '/packages/search/': {'post': OrderedDict([('summary', 'Search over all packages.'), ('description', 'Search over all packages.'), ('operationId', 'search.package'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all packages'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverPackages'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all packages succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPackages')]))]))]))])), ('400', OrderedDict([('description', 'Search across all packages failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['packages'])])}, '/pipelines/new/': {'get': OrderedDict([('summary', 'Get the data needed to create a new pipeline.'), ('description', 'Get the data needed to create a new pipeline.'), ('operationId', 'data_for_new.pipeline'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for the data needed to create a new pipeline resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/NewPipeline')]))]))]))]))])), ('tags', ['pipelines'])])}, '/locations/new_search/': {'get': OrderedDict([('summary', 'Get the data needed to search over all locations.'), ('description', 'Get the data needed to search over all locations.'), ('operationId', 'new_search.location'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request to get the data needed to search across all locations succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/DataForNewSearchOverLocations')]))]))]))]))])), ('tags', ['locations'])])}, '/pipelines/': {'post': OrderedDict([('summary', 'Create a new pipeline.'), ('description', 'Create a new pipeline.'), ('operationId', 'create.pipeline'), ('requestBody', OrderedDict([('description', 'JSON object required to create a new pipeline'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/PipelineCreate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Creation of a new pipeline succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PipelineView')]))]))]))])), ('400', OrderedDict([('description', 'Creation of a new pipeline failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])]), 'search': OrderedDict([('summary', 'Search over all pipelines.'), ('description', 'Search over all pipelines.'), ('operationId', 'search.pipeline'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all pipelines'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverPipelines'})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all pipelines succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPipelines')]))]))]))])), ('400', OrderedDict([('description', 'Search across all pipelines failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])]), 'get': OrderedDict([('summary', 'View all pipelines.'), ('description', 'View all pipelines.'), ('operationId', 'get_many.pipeline'), ('parameters', [{'$ref': '#/components/parameters/items_per_page'}, {'$ref': '#/components/parameters/page'}, {'$ref': '#/components/parameters/order_by_attribute'}, {'$ref': '#/components/parameters/order_by_subattribute'}, {'$ref': '#/components/parameters/order_by_direction'}]), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a collection of pipelines succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPipelines')]))]))]))])), ('400', OrderedDict([('description', 'Request for a collection of pipelines failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['pipelines'])])}, '/packages/{pk}/': {'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the package.')])], 'get': OrderedDict([('summary', 'View an existing package.'), ('description', 'View an existing package.'), ('operationId', 'get.package'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a single package succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PackageView')]))]))]))])), ('404', OrderedDict([('description', 'Request for a single package failed because there is no package resource with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for a single package failed because the user is forbidden from viewing this package resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['packages'])])}, '/packages/': {'search': OrderedDict([('summary', 'Search over all packages.'), ('description', 'Search over all packages.'), ('operationId', 'search.package'), ('requestBody', OrderedDict([('description', 'JSON object required to search over all packages'), ('required', True), ('content', {'application/json': OrderedDict([('schema', {'$ref': '#/components/schemas/SearchOverPackages'}), ('example', {'ObjectSearchOverPackagesExample': {'paginator': {'items_per_page': 10, 'page': 1}, 'query': {'filter': {'complement': [{'attribute': 'description', 'relation': 'like', 'value': '%a%'}, {'complement': {'attribute': 'description', 'relation': 'like', 'value': 'T%'}, 'negation': 'not'}, {'complement': [{'attribute': 'size', 'relation': '<', 'value': 1000}, {'attribute': 'size', 'relation': '>', 'value': 512}], 'conjunction': 'or'}], 'conjunction': 'and'}}}, 'ArraySearchOverPackagesExample': {'paginator': {'items_per_page': 10, 'page': 1}, 'query': {'filter': ['and', [['description', 'like', '%a%'], ['not', ['description', 'like', 'T%']], ['or', [['size', '<', 1000], ['size', '>', 512]]]]]}}})])})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Search across all packages succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPackages')]))]))]))])), ('400', OrderedDict([('description', 'Search across all packages failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['packages'])]), 'get': OrderedDict([('summary', 'View all packages.'), ('description', 'View all packages.'), ('operationId', 'get_many.package'), ('parameters', [{'$ref': '#/components/parameters/items_per_page'}, {'$ref': '#/components/parameters/page'}, {'$ref': '#/components/parameters/order_by_attribute'}, {'$ref': '#/components/parameters/order_by_subattribute'}, {'$ref': '#/components/parameters/order_by_direction'}]), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a collection of packages succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/PaginatedSubsetOfPackages')]))]))]))])), ('400', OrderedDict([('description', 'Request for a collection of packages failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['packages'])])}, '/locations/{pk}/': {'put': OrderedDict([('summary', 'Update an existing location.'), ('description', 'Update an existing location.'), ('operationId', 'update.location'), ('requestBody', OrderedDict([('description', 'JSON object required to update an existing location'), ('required', True), ('content', {'application/json': {'schema': {'$ref': '#/components/schemas/LocationUpdate'}}})])), ('responses', OrderedDict([('200', OrderedDict([('description', 'Updating of an existing location resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/EditALocation')]))]))]))])), ('404', OrderedDict([('description', 'Updating of an existing location resource failed because there is no location with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Updating of an existing location resource failed because the user is forbidden from updating this location resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('400', OrderedDict([('description', 'Updating of an existing location resource failed.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])]), 'get': OrderedDict([('summary', 'View an existing location.'), ('description', 'View an existing location.'), ('operationId', 'get.location'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Request for a single location succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/LocationView')]))]))]))])), ('404', OrderedDict([('description', 'Request for a single location failed because there is no location resource with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Request for a single location failed because the user is forbidden from viewing this location resource.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])]), 'parameters': [OrderedDict([('in', 'path'), ('name', 'pk'), ('required', True), ('schema', OrderedDict([('type', 'string'), ('format', 'uuid')])), ('description', 'The primary key of the location.')])], 'delete': OrderedDict([('summary', 'Delete an existing location.'), ('description', 'Delete an existing location.'), ('operationId', 'delete.location'), ('responses', OrderedDict([('200', OrderedDict([('description', 'Deletion of the location resource succeeded.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/LocationView')]))]))]))])), ('404', OrderedDict([('description', 'Deletion of the location resource failed because there is no location with the specified pk.'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))])), ('403', OrderedDict([('description', 'Deletion of the location resource failed because user is forbidden from performing this action'), ('content', OrderedDict([('application/json', OrderedDict([('schema', OrderedDict([('$ref', '#/components/schemas/ErrorSchema')]))]))]))]))])), ('tags', ['locations'])])}}), ('tags', [OrderedDict([('name', 'locations'), ('description', 'Access to the Location resource')]), OrderedDict([('name', 'packages'), ('description', 'Access to the Package resource')]), OrderedDict([('name', 'pipelines'), ('description', 'Access to the Pipeline resource')]), OrderedDict([('name', 'spaces'), ('description', 'Access to the Space resource')])])])
)



HTTP_METHODS = ('get', 'delete', 'post', 'put')
METHOD_GET = "GET"
METHOD_POST = "POST"
METHOD_DELETE = "DELETE"


indented_wrapper = textwrap.TextWrapper(
    width=80,
    initial_indent=' ' * 4,
    subsequent_indent=' ' * 8)


class ClientError(Exception):
    """Base exception for this module."""


class ValidationError(ClientError):
    """If the arguments to a method are invalid given the API spec."""


class HTTPError(ClientError):
    """If an HTTP request fails unexpectedly."""


class ResponseError(ClientError):
    """if an HTTP response is unexpected given the API spec."""


methods_raise = (ValidationError, HTTPError, ResponseError,)


def _call_url_json(self, url, params=None, method=METHOD_GET, headers=None,
                   assume_json=True, responses_cfg=None):
    """Helper to GET a URL where the expected response is 200 with JSON.

    :param str url: URL to call
    :param dict params: Params to pass as HTTP query string or JSON body
    :param str method: HTTP method (e.g., 'GET')
    :param dict headers: HTTP headers
    :param bool assume_json: set to False if the response body should not be
                             decoded as JSON
    :returns: Dict of the returned JSON or an integer error
            code to be looked up
    """
    method = method.upper()
    logger.debug('%s %s', method, url)
    logger.debug('params:')
    logger.debug(pprint.pformat(params))
    try:
        if method == METHOD_GET or method == METHOD_DELETE:
            response = requests.request(method,
                                        url=url,
                                        params=params,
                                        headers=headers)
        else:
            response = requests.request(method,
                                        url=url,
                                        data=params,
                                        headers=headers)
        logger.debug('Response: %s', response)
        logger.debug('type(response.text): %s ', type(response.text))
        logger.debug('Response content-type: %s',
                     response.headers['content-type'])
    except (urllib3.exceptions.NewConnectionError,
            requests.exceptions.ConnectionError) as err:
        msg = 'Connection error {}'.format(err)
        logger.error(msg)
        raise HTTPError(msg[:30])
    responses_cfg = responses_cfg or {}
    return self._handle_response(response, method, url, responses_cfg)


def _handle_response(self, response, method, url, responses_cfg):
    """Use the OpenAPI-specified responses object to handle how we return the
    response. Warning: a lot of assumptions in here; OpenAPI could definitely
    be used more intelligently and generally here.
    """
    status_code = str(response.status_code)
    response_cfg = responses_cfg.get(status_code)
    if not response_cfg:
        msg = ('Unknown status code {status_code} ("{reason}") returned for'
               '{method} request to {url}'.format(
                    status_code=status_code, reason=response.reason,
                    method=method, url=url))
        logger.warning(msg)
        raise ResponseError(msg)
    resp_descr = response_cfg.get('description', 'Response lacks a description')
    logger.debug('Received an expected response with this description: %s',
                 resp_descr)
    resp_json_cfg = response_cfg.get('content', {}).get('application/json', {})
    if resp_json_cfg:
        try:
            ret = response.json()
        except ValueError:  # JSON could not be decoded
            msg = 'Could not parse JSON from response'
            logger.warning(msg)
            raise ResponseError(msg)
    else:
        return {'error': 'Not a JSON response; this client expects only JSON'
                         ' responses.',
                'response_text': response.text}
    return ret  # How should the happy path response schema inform the return value?


def get_openapi_spec():
    return OPENAPI_SPEC


def get_client_class_name(openapi_spec):
    title = openapi_spec['info']['title']
    return '{}Client'.format(
        ''.join(w.capitalize() for w in title.strip().lower().split()))


def get_client_class_docstring(openapi_spec, resource_classes):
    docstring = []
    title = openapi_spec['info']['title']
    version = openapi_spec['info']['version']
    docstring.append('{} version {} client'.format(title, version))
    description = openapi_spec['info'].get('description')
    if description:
        docstring.append('\n\n')
        docstring.append(textwrap.fill(description, 80))
    if resource_classes:
        docstring.append('\n\n')
        docstring.append(textwrap.fill(
            'The following instance attributes allow interaction with the'
            ' resources that the API exposes. See their documentation:',
            80))
        docstring.append('\n\n')
        for attr_name in sorted(resource_classes):
            docstring.append('- ``self.{}``\n'.format(attr_name))
    if description or resource_classes:
        docstring.append('\n')
    return ''.join(docstring)


def deref(openapi_spec, ref_path):
    """Given an OpenAPI $ref path like '#/components/schemas/ErrorSchema',
    dereference it, i.e., return its corresponding object (typically a dict).
    """
    ref_path_parts = ref_path.strip('#/').split('/')
    dict_ = openapi_spec
    for key in ref_path_parts:
        dict_ = dict_[key]
    return dict_


def recursive_deref(openapi_spec, ref_path, seen_paths=None):
    """Recursively dereference OpenAPI $ref path ``ref_path``, returning a
    2-tuple containing the corresponding object as well as a boolean indicating
    whether the object is circularly referential.
    """
    circular = False
    seen_paths = seen_paths or []
    if ref_path in seen_paths:
        return ref_path, True
    seen_paths.append(ref_path)
    derefed = deref(openapi_spec, ref_path)
    properties = derefed.get('properties')
    if properties:
        for key, cfg in properties.items():
            ref = cfg.get('$ref')
            if ref:
                ret, circ = recursive_deref(
                    openapi_spec, ref, seen_paths=seen_paths)
                derefed['properties'][key] = ret
                if circ:
                    circular = True
    one_of = derefed.get('oneOf')
    if one_of:
        new_one_of = []
        for these in one_of:
            ret, circ = recursive_deref(
                openapi_spec, these['$ref'], seen_paths=seen_paths)
            new_one_of.append(ret)
            if circ:
                circular = True
        derefed['oneOf'] = new_one_of
    return derefed, circular


def ref_path2param_name(ref_path):
    return ref_path.strip('#/').split('/')[-1]


def process_param(parameter, openapi_spec):
    ref_path = parameter['$ref']
    param_name = ref_path2param_name(ref_path)
    param_cfg = deref(openapi_spec, ref_path)
    return param_name, param_cfg


def _reconstruct_params(locals_, args_, kwargs_):
    ret = {}
    for arg_name, arg_cfg in args_.items():
        ret[arg_name] = locals_[arg_name]
    for arg_name, arg_cfg in kwargs_.items():
        try:
            ret[arg_name] = locals_[arg_name]
        except KeyError:
            try:
                ret[arg_name] = arg_cfg['default']
            except KeyError:
                pass
    return ret


openapitype2pythontype = {
    'string': ((str, unicode), 'str or unicode'),
    'integer': ((int,), 'int'),
    'number': ((int, float), 'int or float'),
    'array': ((list,), 'list'),
    'boolean': ((bool,), 'bool'),
}


def get_param_docstring_line(arg, arg_cfg):
    arg_line = [arg]
    arg_type = arg_cfg.get('type', arg_cfg.get('schema', {}).get('type'))
    if arg_type:
        _, arg_type = openapitype2pythontype.get(arg_type, (None, arg_type))
        arg_format = arg_cfg.get('format', arg_cfg.get('schema', {}).get('format'))
        if arg_format:
            arg_line.append(' ({}; {}):'.format(arg_type, arg_format))
        else:
            arg_line.append(' ({}):'.format(arg_type))
    arg_description = arg_cfg.get('description')
    if arg_description:
        if not arg_description.endswith('.'):
            arg_description = '{}.'.format(arg_description)
        arg_line.append(' {}'.format(arg_description))

    arg_enum = arg_cfg.get('enum', arg_cfg.get('schema', {}).get('enum'))
    if arg_enum:
        arg_line.append(' Must be one of {}.'.format(
            ', '.join(repr(e) for e in arg_enum)))
    return '\n' + indented_wrapper.fill(''.join(arg_line))


decapitalize = lambda s: s[:1].lower() + s[1:] if s else ''


def get_returns_docstring_line(openapi_spec, code, cfg):
    return_description = []
    condition = decapitalize(
        cfg.get('description', '{} response'.format(code))).rstrip('.')
    ref = cfg.get('content', {}).get('application/json', {}).get(
        'schema', {}).get('$ref')
    if ref:
        schema = deref(openapi_spec, ref)
        ret_type = {'object': 'dict'}.get(
            schema.get('type'), 'unknown type')
        return_description.append('{}:'.format(ret_type))
        if ret_type == 'dict':
            required_keys = schema.get('required')
            if required_keys:
                return_description.append(
                    ' with key(s): "{}"'.format('", "'.join(required_keys)))
    else:
        return_description.append('\n    unknown type:')
    return_description.append(', if {}.'.format(condition))
    return '\n' + indented_wrapper.fill(''.join(return_description))


def get_method_docstring(op_cfg, args, kwargs, openapi_spec):
    summary = op_cfg.get('summary')
    description = op_cfg.get('description')
    if not summary:
        return None
    docstring = [summary]
    if description and description != summary:
        docstring.append('\n\n')
        docstring.append(description)
    if args or kwargs:
        docstring.append('\n\n')
        docstring.append('Args:')
    for arg, arg_cfg in args.items():
        docstring.append(get_param_docstring_line(arg, arg_cfg))
    for kwarg, kwarg_cfg in kwargs.items():
        docstring.append(get_param_docstring_line(kwarg.replace('_param', ''), kwarg_cfg))
    docstring.append('\n\n')
    docstring.append('Returns:')
    for code, cfg in op_cfg.get('responses').items():
        docstring.append(get_returns_docstring_line(openapi_spec, code, cfg))
    docstring.append('\n\n')
    docstring.append('Raises:')
    for exc in methods_raise:
        docstring.append('\n' + indented_wrapper.fill('{}: {}'.format(
            exc.__name__, exc.__doc__)))
    return ''.join(docstring)


def _validate_min(param_name, param_val, param_schema):
    param_min = param_schema.get('minimum')
    if param_min:
        if param_val < param_min:
            raise ValidationError(
                'Value {} for argument "{}" must be {} or greater.'.format(
                    param_val, param_name, param_min))


def _validate_max(param_name, param_val, param_schema):
    param_max = param_schema.get('maximum')
    if param_max:
        if param_val > param_max:
            raise ValidationError(
                'Value {} for argument "{}" is greater than the maximum'
                ' allowed value {}.'.format(
                    param_val, param_name, param_max))


def _validate_enum(param_name, param_val, param_schema):
    param_enum = param_schema.get('enum')
    if param_enum:
        if param_val not in param_enum:
            raise ValidationError(
                'Value {} for argument "{}" must be one of {}'.format(
                    repr(param_val), param_name,
                    ', '.join(repr(e) for e in param_enum)))


def _is_uuid(inp):
    err = ValidationError('"{}" is not a valid UUID'.format(inp))
    try:
        recomposed = []
        parts = inp.split('-')
        if [len(p) for p in parts] != [8, 4, 4, 4, 12]:
            raise err
        for part in parts:
            new_part = ''.join(c for c in part if c in '0123456789abcdef')
            recomposed.append(new_part)
        recomposed = '-'.join(recomposed)
    except Exception:
        raise err
    if recomposed != inp:
        raise err


format_validators = {
    'uuid': _is_uuid,
}


def _validate_format(param_name, param_val, param_schema):
    param_format = param_schema.get('format')
    if not param_format:
        return
    validator = format_validators.get(param_format)
    if not validator:
        return
    validator(param_val)


def _validate(params, args_, kwargs_):
    """Validate user-supplied ``params`` using the parameter configurations
    described in the ``args_`` and ``kwargs_`` dicts. Raise a
    ``ValidationError`` if a value is invalid. Also remove unneeded
    values from ``params``, which is what gets sent (as request body or query
    params) in the request.  TODO: we need to validate complex objects in this
    function but this is a non-trivial issue.
    """
    to_delete = []
    for param_name, param_val in params.items():
        param_required = False
        param_cfg = args_.get(param_name)
        if param_cfg:
            param_required = True
        else:
            param_cfg = kwargs_[param_name]
        param_schema = param_cfg.get('schema', {})
        param_type = param_schema.get('type', param_cfg.get('type'))
        if not param_type:
            continue
        if param_type == 'object':
            if not param_val:
                if param_required:
                    raise ValidationError(
                        'Property {} is required'.format(param_name))
                continue
            # TODO: we need to validate all of the properties of this object:
            # for key, val in param_val.items():
            #     # validate against param_cfg['properties'][key]
            continue
        param_type, _ = openapitype2pythontype.get(param_type, (None, None))
        if not param_type:
            continue
        if ((param_val is None) and
                (not param_required) and
                (not isinstance(None, param_type))):
            to_delete.append(param_name)
            continue
        if not isinstance(param_val, param_type):
            raise ValidationError(
                'Value "{}" for argument "{}" is of type {}; it must be of type(s)'
                ' {}'.format(param_val, param_name, type(param_val),
                             ', '.join(str(t) for t in param_type)))
        _validate_min(param_name, param_val, param_schema)
        _validate_max(param_name, param_val, param_schema)
        _validate_format(param_name, param_val, param_schema)
        _validate_enum(param_name, param_val, param_schema)
        param_in = param_cfg.get('in')
        if param_in == 'path':
            to_delete.append(param_name)
    for td in to_delete:
        del params[td]


def _get_kwarg_names(kwargs_):
    if not kwargs_:
        return ''
    kwarg_names=[]
    for kwarg_name, cfg in sorted(kwargs_.items()):
        default = cfg.get('default')
        if not default:
            default = cfg.get('schema', {}).get('default')
        kwarg_names.append('{}={}'.format(kwarg_name, repr(default)))
    return ', ' + ', '.join(kwarg_names)


def _serialize_params(self, params, request_body_config):
    rb_json_cfg = request_body_config.get(
        'content', {}).get('application/json')
    if not rb_json_cfg:
        return params
    return json.dumps(params)


def get_method_signature(method_name, arg_names, kwarg_names):
    ret = 'def {method_name}(self{arg_names}{kwarg_names}):'.format(
        method_name=method_name, arg_names=arg_names, kwarg_names=kwarg_names)
    indent = ' ' * len('def {}('.format(method_name))
    return textwrap.TextWrapper(width=80, subsequent_indent=indent).fill(ret)


def generate_method_code(method_name, docstring, args_, kwargs_):
    arg_names = ''
    if args_:
        arg_names = ', ' + ', '.join(args_)
    kwarg_names = _get_kwarg_names(kwargs_)
    method_sig = get_method_signature(method_name, arg_names, kwarg_names)

    return '''
{method_sig}
    """{docstring}
    """
    locals_copy = locals().copy()
    format_kwargs = {{key: locals_copy[key] for key in args_}}
    path_ = globals()['path_'].format(**format_kwargs)
    url = self.url + path_
    params = _reconstruct_params(locals(), args_, kwargs_)
    _validate(params, args_, kwargs_)
    params = self._serialize_params(params, request_body_config)
    return self._call_url_json(
        url, params=params, method=http_method.upper(),
        headers=self.get_auth_headers(), responses_cfg=responses_cfg)
'''.format(method_sig=method_sig, docstring=docstring)


def _get_request_body_schema(openapi_spec, operation_config):
    request_body = operation_config.get('requestBody')
    if not request_body:
        return None
    try:
        rb_ref_path = request_body[
            'content']['application/json']['schema']['$ref']
    except KeyError:
        return None
    schema, _ = recursive_deref(openapi_spec, rb_ref_path)
    return schema


def _get_request_body_args_kwargs(openapi_spec, op_cfg):
    args = OrderedDict()
    kwargs = {}
    rb_schema = _get_request_body_schema(openapi_spec, op_cfg)
    if rb_schema:
        for arg_name in sorted(rb_schema.get('required', [])):
            args[arg_name] = rb_schema['properties'][arg_name]
        for kwarg, cfg in rb_schema['properties'].items():
            if kwarg in args:
                continue
            kwargs[kwarg] = cfg
    return args, kwargs


def get_method(openapi_spec, path, path_params, http_method, op_cfg):
    """Return a Python method, its name and its namespace, given the operation
    defined by the unique combination of ``path`` and ``http_method``. E.g.,
    path /locations/{pk}/ and http_method GET will return a method named
    ``get`` with namespace ``location``. The ``get`` method will be assigned to
    a ``LocationClient`` instance of the ``Client`` instance, thus allowing the
    caller to call ``myclient.location.get(pk_of_a_resource)``.
    """
    # pylint: disable=exec-used,too-many-locals
    method_name, namespace = op_cfg['operationId'].split('.')
    rb_args, rb_kwargs = _get_request_body_args_kwargs(openapi_spec, op_cfg)
    parameters = op_cfg.get('parameters', [])
    args_ = OrderedDict()
    kwargs_ = {}
    for parameter in path_params:
        args_[parameter['name']] = parameter
    for param_name, param_cfg in rb_args.items():
        args_[param_name] = param_cfg
    for param_name, param_cfg in rb_kwargs.items():
        kwargs_[param_name] = param_cfg
    for parameter in parameters:
        param_name, param_cfg = process_param(parameter, openapi_spec)
        if param_cfg.get('required', True):
            args_[param_name] = param_cfg
        else:
            kwargs_[param_name] = param_cfg
    docstring = get_method_docstring(op_cfg, args_, kwargs_, openapi_spec)
    method_ = generate_method_code(method_name, docstring, args_, kwargs_)
    # This is necessary so that the method is a closure over these values
    temp_globals = globals().copy()
    temp_globals.update({'path_': path,
                         'args_': args_,
                         'kwargs_': kwargs_,
                         'http_method': http_method,
                         'responses_cfg': op_cfg['responses'],
                         'request_body_config': op_cfg.get('requestBody', {}),
                         })
    exec method_ in temp_globals, locals()
    return locals()[method_name], method_name, namespace


def get_namespaces_methods(openapi_spec):
    """Return a dict from namespaces to method names to methods, e.g.,::

        >>> {'location': {'get': <function get at 0x108dccc08>,
        ...               'get_many': <function get_many at 0x108dcca28>,
        ...               ...},
        ...  'package': {'get': <function get at 0x108dcc7d0>,
        ...              ...},
        ...  ...}
    """
    methods = {}
    for path, cfg in openapi_spec['paths'].items():
        path_params = cfg.get('parameters', [])
        for http_method, op_cfg in cfg.items():
            if http_method in HTTP_METHODS:
                method, method_name, namespace = get_method(
                    openapi_spec, path, path_params, http_method, op_cfg)
                methods.setdefault(namespace, {})[method_name] = method
    return methods


def get_get_auth_headers_meth(openapi_spec):
    """Return a method for the client class that returns the authentication
    headers needed to make requests. Just hard-coding this for now to be
    specific to the AM SS API, but it should be generalized to parse the
    OpenAPI spec.
    """
    # pylint: disable=unused-argument
    def get_auth_headers(self):
        return {'Authorization': 'ApiKey {}:{}'.format(
            self.username,
            self.api_key)}
    return get_auth_headers


def get_base_client_class(openapi_spec):

    def __init__(self, username, api_key, url):
        """Args:
            username (str): The username to use when authenticating to the API.
            api_key (str): The API key to use when authenticating to the API.
            url (str): The URL of the API.
        """
        self.username = username
        self.api_key = api_key
        self.url = url.rstrip('/') + self.openapi_spec['servers'][0]['url']

    def get_auth_headers(self):
        """Return the authorization header(s) as a dict."""
        return {'Authorization': 'ApiKey {}:{}'.format(
            self.username,
            self.api_key)}

    return type(
        'BaseClient',
        (object,),
        {'__init__': __init__,
         'get_auth_headers': get_auth_headers,
         'openapi_spec': openapi_spec,
         '_call_url_json': _call_url_json,
         '_handle_response': _handle_response,
         '_serialize_params': _serialize_params,
        })


def get_init_meth():
    def __init__(self, username, api_key, url):
        super(self.__class__, self).__init__(username, api_key, url)
        for resource_name, resource_class in self.resource_classes.items():
            setattr(self, resource_name, resource_class(username, api_key, url))
    return __init__


def get_rsrc_cls_docstring(resource_name):
    return 'Provides access to the {} resource'.format(resource_name)


def metaprog_client_class():
    """Define and return the client class and its name.
    """
    openapi_spec = get_openapi_spec()
    client_class_name_ = get_client_class_name(openapi_spec)
    BaseClient = get_base_client_class(openapi_spec)
    namespaces_methods = get_namespaces_methods(openapi_spec)
    resource_classes = {}
    for namespace, rsrc_methods in namespaces_methods.items():
        cls_name = namespace.capitalize() + 'Client'
        rsrc_methods['__doc__'] = get_rsrc_cls_docstring(namespace)
        rsrc_cls = type(cls_name, (BaseClient,), rsrc_methods)
        resource_classes[namespace] = rsrc_cls
    client_class_docstring = get_client_class_docstring(
        openapi_spec, resource_classes)
    attributes = {'__init__': get_init_meth(),
                  'resource_classes': resource_classes,
                  '__doc__': client_class_docstring}
    client_class_ = type(
        client_class_name_,  # e.g., ArchivematicaStorageServiceAPIClass
        (BaseClient,),  # superclass(es)
        attributes  # class attributes and methods (descriptors)
    )
    return client_class_, client_class_name_


client_class, client_class_name = metaprog_client_class()
globals()[client_class_name] = client_class

# pylint: disable=undefined-all-variable
__all__ = ('client_class', client_class_name)
