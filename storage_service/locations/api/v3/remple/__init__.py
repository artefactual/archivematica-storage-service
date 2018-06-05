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
    UUID_PATT,
    ID_PATT,
    get_collection_targeting_regex,
    get_member_targeting_regex,
)
from . import utils
from .schemata import ValidModelObject

__all__ = ('API', 'UUID_PATT', 'ID_PATT', 'utils', 'ReadonlyResources',
           'QueryBuilder', 'Resources', 'ValidModelObject',
           'get_collection_targeting_regex', 'get_member_targeting_regex',)
