"""Remple Route Builder

Defines the ``RouteBuilder`` class whose ``register_resources`` method takes a
dict representing a resource configuration. Once resources are registered, the
``get_urlpatterns`` method can be called to return a list of URL patterns that
can be passed to Django's ``django.conf.urls.include``. Example usage::

    >>> resources = {...}
    >>> route_builder = RouteBuilder()
    >>> route_builder.register_resources(resources)
    >>> urls = route_builder.get_urlpatterns()
    >>> urlpatterns = [url(r'v3/', include(urls))]

All resources registered with the ``RouteBuilder`` are given endpoints that
follow this pattern::

    +-----------------+-------------+----------------------------+--------+
    | Purpose         | HTTP Method | Path                       | Method |
    +-----------------+-------------+----------------------------+--------+
    | Create new      | POST        | /<cllctn_name>/            | create |
    | Create data     | GET         | /<cllctn_name>/new/        | new    |
    | Read all        | GET         | /<cllctn_name>/            | index  |
    | Read specific   | GET         | /<cllctn_name>/<id>/       | show   |
    | Update specific | PUT         | /<cllctn_name>/<id>/       | update |
    | Update data     | GET         | /<cllctn_name>/<id>/edit/  | edit   |
    | Delete specific | DELETE      | /<cllctn_name>/<id>/       | delete |
    | Search          | SEARCH      | /<cllctn_name>/            | search |
    | Search          | POST        | /<cllctn_name>/search/     | search |
    | Search data     | GET         | /<cllctn_name>/new_search/ | search |
    +-----------------+-------------+----------------------------+--------+

Example resource dict::

    >>> resources = {
    ...     'dog': {'resource_cls': Dogs},
    ...     'cat': {'resource_cls': Cats}}

.. note:: To remove the search-related routes for a given resource, create a
   ``'searchable'`` key with value ``False`` in the configuration for the
   resource in the ``RESOURCES`` dict. E.g., ``'location': {'searchable':
   False}`` will make the /locations/ resource non-searchable.

.. note:: All resources expose the same endpoints. If a resource needs special
   treatment, it should be done at the corresponding class level. E.g., if
   ``POST /packages/`` (creating a package) is special, then do special stuff
   in ``resources.py::Packages.create``. Similarly, if packages are indelible,
   then ``resources.py::Packages.delete`` should return 404.
"""

from __future__ import absolute_import
from collections import namedtuple
from functools import partial
from itertools import chain
import logging
import os
import pprint
import re
import string

from django.conf.urls import url
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.template import Template, Context
from django.views.decorators.csrf import csrf_exempt
import inflect
from tastypie.models import ApiKey

from .constants import (
    METHOD_NOT_ALLOWED_STATUS,
    UNAUTHORIZED_MSG,
    FORBIDDEN_STATUS,
)
from .openapi import OpenAPI, CustomEndPoint


logger = logging.getLogger(__name__)

UUID_PATT = r'\w{8}-\w{4}-\w{4}-\w{4}-\w{12}'
ID_PATT = r'\d+'
ROUTE_NAME_CHARS = string.letters + '_'

inflp = inflect.engine()
inflp.classical()


class RouteBuilder(OpenAPI):
    """A builder of routes: register resources and get URL patterns.

    Typical usage involves passing dict of resource configuration to
    ``register_resources`` and then calling ``get_urlpatterns`` to retrieve a
    list of corresponding Django ``url`` instances::

        >>> resources = {'user': {'resource_cls': Users}}  # Users is a resources.Resources sub-class
        >>> api = API(api_version='0.1.0', service_name='User City!')
        >>> api.register_resources(resources)
        >>> urls = api.get_urlpatterns()  # Include these in Django urlpatterns
    """

    inflp = inflp

    RESOURCE_ACTIONS = ('create',
                        'delete',
                        'edit',
                        'index',
                        'new',
                        'show',
                        'update')
    MUTATING_ACTIONS = ('create', 'delete', 'edit', 'new', 'update')
    COLLECTION_TARGETING = ('create', 'index')
    MEMBER_TARGETING = ('delete', 'show', 'update')
    DEFAULT_METHOD = 'GET'
    ACTIONS2METHODS = {'create': 'POST',
                       'delete': 'DELETE',
                       'update': 'PUT'}

    def __init__(self, *args, **kwargs):
        self.routes = {}
        self.resources = None
        super(RouteBuilder, self).__init__(*args, **kwargs)

    def register_route(self, route):
        """Register a ``Route()`` instance by breaking it apart and storing it
        in ``self.routes``, keyed by its regex and then by its HTTP method.
        """
        config = self.routes.get(route.regex, {})
        config['route_name'] = route.name
        http_methods_config = config.get('http_methods', {})
        http_methods_config[route.http_method] = (
            route.resource_cls, route.method_name)
        config['http_methods'] = http_methods_config
        self.routes[route.regex] = config

    def is_authenticated(self, request):
        """Checks for TastyPie ApiKey HTTP header-based authorization.

        Requires a header named ``'Authorization'`` that valuates to a string
        of the form ``'ApiKey <username>:<api_key>'``.
        """
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        logger.info('API Beta: authenticating with %s', auth_header)
        if not auth_header:
            logger.info('API Beta: no Authorization header')
            return False
        try:
            username_key = auth_header.split()[-1]
            username, key = username_key.split(':', 1)
        except ValueError:
            logger.info('API Beta: unable to extract username and key from'
                        ' Authorization header %s', auth_header)
            return False
        try:
            user = User.objects.get(username=username)
            api_key = str(ApiKey.objects.get(user=user)).split()[0]
        except (User.DoesNotExist, ApiKey.DoesNotExist):
            logger.info('API Beta: unable to find a user and ApiKey model that'
                        ' match username "%s" and API key "%s"', user, api_key)
            return False
        if key == api_key:
            return True
        logger.info('API Beta: supplied key "%s" and known key "%s" are not'
                    ' equal', key, api_key)
        return False

    def get_urlpatterns(self):
        """Return ``urlpatterns_``, a list of Django ``url`` instances that
        cause the appropriate instance method to be called for a given request.
        Because Django does not allow the HTTP method to determine what is
        called, we must supply a view to ``url`` as an anonymous function with
        a closure over the route "config", which the anonymous function can use
        to route the request to the appropriate method call. For example,
        ``GET /pipelines/`` and ``POST /pipelines/`` are handled by the same
        function, but ultimately the former is routed to ``Pipelines().index``
        and the latter to ``Pipelines().create``.
        """
        urlpatterns_ = []
        for regex, config in self.routes.items():
            route_name = config['route_name']

            def resource_callable(config, request, **kwargs):
                http_methods_config = config['http_methods']
                try:
                    resource_cls, method_name = http_methods_config[
                        request.method]
                except KeyError:
                    return JsonResponse(
                        method_not_allowed(
                            request.method, list(http_methods_config.keys())),
                        status=METHOD_NOT_ALLOWED_STATUS)
                instance = resource_cls(
                    request, server_path=self.get_dflt_server_path(),
                    other_resources=self.resources)
                if self.is_authenticated(request):
                    method = getattr(instance, method_name)
                    response, status = method(**kwargs)
                else:
                    logger.warning(UNAUTHORIZED_MSG)
                    response, status = UNAUTHORIZED_MSG, FORBIDDEN_STATUS
                return JsonResponse(response, status=status, safe=False)

            urlpatterns_.append(url(
                regex,
                # Sidestep Python's late binding:
                view=csrf_exempt(partial(resource_callable, config)),
                name=route_name))
        urlpatterns_ += self.get_schema_doc_urlpatterns()
        return urlpatterns_

    def yield_standard_routes(self, rsrc_member_name, resource_cls):
        """Yield the ``Route()``s needed to configure standard CRUD actions on the
        resource with member name ``rsrc_member_name``.
        """
        pk_patt = {'uuid': UUID_PATT, 'id': ID_PATT}.get(
            resource_cls.primary_key, UUID_PATT)
        rsrc_collection_name = inflp.plural(rsrc_member_name)
        for action in self.RESOURCE_ACTIONS:
            method_name = action
            http_method = self.ACTIONS2METHODS.get(action, self.DEFAULT_METHOD)
            api_v_slug = self.get_api_version_slug()
            if action in self.COLLECTION_TARGETING:
                route_name = '{}_{}'.format(api_v_slug, rsrc_collection_name)
                regex = get_collection_targeting_regex(rsrc_collection_name)
            elif action in self.MEMBER_TARGETING:
                route_name = '{}_{}'.format(api_v_slug, rsrc_member_name)
                regex = get_member_targeting_regex(rsrc_collection_name, pk_patt)
            elif action == 'new':
                route_name = '{}_{}_new'.format(
                    api_v_slug, rsrc_collection_name)
                regex = get_collection_targeting_regex(
                    rsrc_collection_name, modifiers=['new'])
            else:  # edit is default case
                route_name = '{}_{}_edit'.format(
                    api_v_slug, rsrc_member_name)
                regex = get_member_targeting_regex(
                    rsrc_collection_name, pk_patt, modifiers=['edit'])
            yield Route(name=route_name,
                        regex=regex,
                        http_method=http_method,
                        resource_cls=resource_cls,
                        method_name=method_name)

    def yield_custom_routes(self, rsrc_member_name, resource_cls):
        api_v_slug = self.get_api_version_slug()
        pk_patt = {'uuid': UUID_PATT, 'id': ID_PATT}.get(
            resource_cls.primary_key, UUID_PATT)
        rsrc_collection_name = self.inflp.plural(rsrc_member_name)
        for attr_name in dir(resource_cls):
            if attr_name.startswith('_'):
                continue
            custom_endpoint = getattr(resource_cls, attr_name)
            if not isinstance(custom_endpoint, CustomEndPoint):
                continue
            route_name = '{}_{}_{}'.format(
                api_v_slug, rsrc_member_name, custom_endpoint.action)
            yield Route(name=route_name,
                        regex=openapi_path2regex(custom_endpoint.path,
                                                 rsrc_collection_name, pk_patt),
                        http_method=custom_endpoint.http_method.upper(),
                        resource_cls=resource_cls,
                        method_name=custom_endpoint.method_name)

    def register_routes_for_resource(self, rsrc_member_name, rsrc_config):
        """Register all of the routes generable for the resource with member
        name ``rsrc_member_name`` and with configuration ``rsrc_config``. The
        ``rsrc_config`` can control whether the resource is searchable.
        """
        routes = []
        if rsrc_config.get('searchable', True):
            routes.append(self.yield_search_routes(
                rsrc_member_name, rsrc_config['resource_cls']))
        routes.append(self.yield_standard_routes(
            rsrc_member_name, rsrc_config['resource_cls']))
        routes.append(self.yield_custom_routes(
            rsrc_member_name, rsrc_config['resource_cls']))
        for route in chain(*routes):
            self.register_route(route)

    def register_resources(self, resources_):
        """Register all of the routes generable for each resource configured in
        the ``resources_`` dict.
        """
        self.resources = resources_
        for rsrc_member_name, rsrc_config in resources_.items():
            self.register_routes_for_resource(rsrc_member_name, rsrc_config)

    def yield_search_routes(self, rsrc_member_name, resource_cls):
        """Yield the ``Route()``s needed to configure search across the resource
        with member name ``rsrc_member_name``.
        """
        rsrc_collection_name = inflp.plural(rsrc_member_name)
        api_v_slug = self.get_api_version_slug()
        yield Route(name='{}_{}'.format(api_v_slug, rsrc_collection_name),
                    regex=get_collection_targeting_regex(rsrc_collection_name),
                    http_method='SEARCH',
                    resource_cls=resource_cls,
                    method_name='search')
        yield Route(name='{}_{}_search'.format(api_v_slug, rsrc_collection_name),
                    regex=get_collection_targeting_regex(
                        rsrc_collection_name, modifiers=['search']),
                    http_method='POST',
                    resource_cls=resource_cls,
                    method_name='search')
        yield Route(name='{}_{}_new_search'.format(api_v_slug, rsrc_collection_name),
                    regex=get_collection_targeting_regex(
                        rsrc_collection_name, modifiers=['new_search']),
                    http_method='GET',
                    resource_cls=resource_cls,
                    method_name='new_search')

    def schema_view(self, request):
        """Serve the OpenAPI YAML that defines this API in an HTML <pre>, i.e.,
        human-readable.
        """
        schema = self.generate_open_api_spec()
        raw_code = self.to_yaml(schema).encode('utf8')
        title = '{} ({})'.format(schema['info']['title'],
                                 schema['info']['version'])
        return HttpResponse(
            Template(raw_code_template).render(Context(
                {'title': title, 'raw_code': raw_code})))

    def yaml_schema_view(self, request):
        """Serve the raw OpenAPI YAML that defines this API."""
        schema = self.generate_open_api_spec()
        schema_yaml = self.to_yaml(schema)
        return HttpResponse(schema_yaml)

    def doc_view(self, request):
        """Serve the Swagger UI HTML for this API."""
        api_v_slug = self.get_api_version_slug()
        yaml_url = reverse('{}_yaml'.format(api_v_slug))
        schema_url = reverse('{}_schema'.format(api_v_slug))
        client_url = reverse('{}_client'.format(api_v_slug))
        return render(request, 'locations/api/beta/openapi.html', locals())

    def client_view(self, request):
        """Create the Python client module using the clientbuilder.py module
        and inserting the OpenAPI spec data structure into the newly created
        file as a constant. Then serve the script as a string in a JSON dict as
        the value of the 'client' attribute. Serving the script as JSON gets
        around encoding complications.
        """
        schema = self.generate_open_api_spec()
        client_builder_path = os.path.join(
            os.path.dirname(__file__),
            'clientbuilder.py')
        client = []
        with open(client_builder_path) as filei:
            for line in filei:
                if line.startswith('OPENAPI_SPEC = None'):
                    client.append('OPENAPI_SPEC = (\n    {}\n)'.format(
                        pprint.pformat(schema)))
                else:
                    client.append(line)
        raw_code = ''.join(client)
        return JsonResponse({'client': raw_code})

    def get_schema_doc_urlpatterns(self):
        """Return a list of Django ``url`` instances that configure the / and
        /doc/ paths to return the OpenAPI YAML and the Swagger UI, respectively.
        """
        api_v_slug = self.get_api_version_slug()
        return [
            url(r'^$', self.schema_view, name='{}_schema'.format(api_v_slug)),
            url(r'^yaml/$', self.yaml_schema_view,
                name='{}_yaml'.format(api_v_slug)),
            url(r'^doc/$', self.doc_view, name='{}_doc'.format(api_v_slug)),
            url(r'^client/$', self.client_view,
                name='{}_client'.format(api_v_slug)),
        ]


raw_code_template = '''
<!DOCTYPE html>
<html>
  <head>
    <title>{{ title }}</title>
  </head>
<body>
  <pre>
<code>{{ raw_code }}</code>
  </pre>
</body>
</html>
'''


# A "route" is a unique combination of path regex, route name, HTTP method, and
# class/method to call when the path regex and HTTP method match a request.
# Note that because of how Django's ``url`` works, multiple distinct routes can
# have the same ``url`` instance with the same name; e.g., POST /pipelines/ and
# GET /pipelines/ are both handled by the "pipelines" ``url``.
Route = namedtuple('Route', 'name regex http_method resource_cls method_name')


def get_collection_targeting_regex(rsrc_collection_name, modifiers=None):
    """Return a regex of the form '^<rsrc_collection_name>/$'
    with optional trailing modifiers, e.g., '^<rsrc_collection_name>/new/$'.
    """
    if modifiers:
        return r'^{rsrc_collection_name}/{modifiers}/$'.format(
            rsrc_collection_name=rsrc_collection_name,
            modifiers='/'.join(modifiers))
    return r'^{rsrc_collection_name}/$'.format(
        rsrc_collection_name=rsrc_collection_name)


def get_member_targeting_regex(rsrc_collection_name, pk_patt, modifiers=None):
    """Return a regex of the form '^<rsrc_collection_name>/<pk>/$'
    with optional modifiers after the pk, e.g.,
    '^<rsrc_collection_name>/<pk>/edit/$'.
    """
    if modifiers:
        return (r'^{rsrc_collection_name}/(?P<pk>{pk_patt})/'
                r'{modifiers}/$'.format(
                    rsrc_collection_name=rsrc_collection_name,
                    pk_patt=pk_patt,
                    modifiers='/'.join(modifiers)))
    return r'^{rsrc_collection_name}/(?P<pk>{pk_patt})/$'.format(
        rsrc_collection_name=rsrc_collection_name, pk_patt=pk_patt)


def method_not_allowed(tried_method, accepted_methods):
    return {'error': 'The {} method is not allowed for this resources. The'
                     ' accepted methods are: {}'.format(
                         tried_method, ', '.join(accepted_methods))}


def openapi_path2regex(path, rsrc_collection_name, pk_patt):
    path_var_patt = re.compile(r'\{(.+)\}')

    def replacer(match):
        return r'(?P<' + match.groups()[0] + r'>' + pk_patt + r')'

    return (r'^' + rsrc_collection_name + r'/' +
            path_var_patt.sub(replacer, path) + r'$')
