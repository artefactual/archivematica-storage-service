"""Remple: REST Simple

Usage::

    >>> from remple import API, Resources
    >>> class Users(Resources):
    ...     model_cls = User  # A Django model class
    ...     schema_cls = UserSchema  # A Formencode class
    >>> resources = {'user': {'resource_cls': Users}}
    >>> api = API(api_version='0.1.0', service_name='User City!')
    >>> api.register_resources(resources)
    >>> urls = api.get_urlpatterns()  # Include thes in Django urlpatterns
"""

from __future__ import absolute_import

from .resources import Resources, ReadonlyResources
from .querybuilder import QueryBuilder
from .routebuilder import RouteBuilder as API
from .routebuilder import (
    ID_PATT,
    UUID_PATT,
    get_collection_targeting_regex,
    get_member_targeting_regex,
)
from .openapi import (
    CustomEndPoint,
    schema_name2path,
    get_error_schema_path,
    get_ref_response,
)
from . import utils
from .schemata import ResourceURI
from .constants import (
    OK_STATUS,
    NOT_FOUND_STATUS,
    UNAUTHORIZED_MSG,
    FORBIDDEN_STATUS,
)

__all__ = (
    'API',
    'CustomEndPoint',
    'FORBIDDEN_STATUS',
    'ID_PATT',
    'NOT_FOUND_STATUS',
    'OK_STATUS',
    'QueryBuilder',
    'ReadonlyResources',
    'Resources',
    'ResourceURI',
    'UNAUTHORIZED_MSG',
    'UUID_PATT',
    'get_collection_targeting_regex',
    'get_error_schema_path',
    'get_ref_response',
    'get_member_targeting_regex',
    'schema_name2path',
    'utils',
)
