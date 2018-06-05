# -*- coding: utf8 -*-
"""Tests for the api.v3.urls module."""

from __future__ import print_function

import pytest

from locations.api.v3.remple import (
    API,
    UUID_PATT,
    ID_PATT,
    get_collection_targeting_regex,
    get_member_targeting_regex,
    Resources,
)
from locations.api.v3.resources import (
    Locations,
    Packages,
    Spaces,
    Pipelines,
)


class MyPackages(Packages):
    # Pretend pk for /packages/ is int id
    primary_key = 'id'


def test_urls_construction():
    """Tests that we can configure URL routing for RESTful resources using a
    simple dict of resource member names.
    """
    # Configure routing and get a list of corresponding Django ``url``
    # instances as ``urlpatterns``
    resources = {
        'location': {'resource_cls': Locations},
        'package': {'resource_cls': MyPackages},
        # Make /spaces/ non-searchable
        'space': {'resource_cls': Spaces, 'searchable': False},
        'pipeline': {'resource_cls': Pipelines},
    }

    api = API(api_version='0.1.0', service_name='Monkey')
    api.register_resources(resources)
    urlpatterns = api.get_urlpatterns()

    # Make assertions about ``urlpatterns``
    urlpatterns_names_regexes = sorted(
        [(up.name, up.regex.pattern) for up in urlpatterns])
    expected = [
        ('location', '^locations/(?P<pk>{})/$'.format(UUID_PATT)),
        ('location_edit',
         '^locations/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('locations', '^locations/$'),
        ('locations_new', '^locations/new/$'),
        ('locations_new_search', '^locations/new_search/$'),
        ('locations_search', '^locations/search/$'),
        # Note the ID_PATT for /packages/ because of pk_patt above
        ('package', '^packages/(?P<pk>{})/$'.format(ID_PATT)),
        ('package_edit',
         '^packages/(?P<pk>{})/edit/$'.format(ID_PATT)),
        ('packages', '^packages/$'),
        ('packages_new', '^packages/new/$'),
        ('packages_new_search', '^packages/new_search/$'),
        ('packages_search', '^packages/search/$'),
        ('pipeline', '^pipelines/(?P<pk>{})/$'.format(UUID_PATT)),
        ('pipeline_edit',
         '^pipelines/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('pipelines', '^pipelines/$'),
        ('pipelines_new', '^pipelines/new/$'),
        ('pipelines_new_search', '^pipelines/new_search/$'),
        ('pipelines_search', '^pipelines/search/$'),
        # Note that the /spaces/ resource has no search-related routes.
        ('space', '^spaces/(?P<pk>{})/$'.format(UUID_PATT)),
        ('space_edit', '^spaces/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('spaces', '^spaces/$'),
        ('spaces_new', '^spaces/new/$')
    ]
    assert urlpatterns_names_regexes == expected

    # Make assertions about ``api.routes``
    assert api.routes[r'^locations/$'] == {
        'http_methods': {'GET': (Locations, 'index'),
                         'POST': (Locations, 'create'),
                         'SEARCH': (Locations, 'search')},
        'route_name': 'locations'}
    assert api.routes[
            r'^locations/(?P<pk>{})/$'.format(UUID_PATT)] == {
        'http_methods': {'DELETE': (Locations, 'delete'),
                         'GET': (Locations, 'show'),
                         'PUT': (Locations, 'update')},
        'route_name': 'location'}
    assert api.routes[
            r'^locations/(?P<pk>{})/edit/$'.format(UUID_PATT)] == {
        'http_methods': {'GET': (Locations, 'edit')},
        'route_name': 'location_edit'}
    assert api.routes['^locations/new/$'] == {
        'http_methods': {'GET': (Locations, 'new')},
        'route_name': 'locations_new'}
    assert api.routes['^locations/new_search/$'] == {
        'http_methods': {'GET': (Locations, 'new_search')},
        'route_name': 'locations_new_search'}
    assert api.routes['^locations/search/$'] == {
        'http_methods': {'POST': (Locations, 'search')},
        'route_name': 'locations_search'}
    assert '^spaces/search/$' not in api.routes
    assert '^pipelines/search/$' in api.routes
    assert '^packages/search/$' in api.routes
    assert r'^packages/(?P<pk>{})/$'.format(ID_PATT) in api.routes
    assert r'^packages/(?P<pk>{})/$'.format(
        UUID_PATT) not in api.routes


def test_regex_builders():
    """Test that the regex-building functions can build the correct regexes
    given resource names as input.
    """
    # Collection-targeting regex builder
    assert r'^frogs/$' == get_collection_targeting_regex('frogs')
    assert r'^frogs/legs/$' == get_collection_targeting_regex(
        'frogs', modifiers=['legs'])
    assert r'^frogs/legs/toes/$' == get_collection_targeting_regex(
        'frogs', modifiers=['legs', 'toes'])
    assert r'^frogs/l/e/g/s/$' == get_collection_targeting_regex(
        'frogs', modifiers='legs')
    with pytest.raises(TypeError):
        get_collection_targeting_regex('frogs', modifiers=1)

    # Member-targeting regex builder
    assert r'^frogs/(?P<pk>{})/$'.format(
        UUID_PATT) == get_member_targeting_regex(
            'frogs', UUID_PATT)
    assert r'^frogs/(?P<pk>{})/legs/$'.format(
        ID_PATT) == get_member_targeting_regex(
            'frogs', ID_PATT, modifiers=['legs'])
    assert r'^frogs/(?P<pk>{})/legs/toes/$'.format(
        UUID_PATT) == get_member_targeting_regex(
            'frogs', UUID_PATT, modifiers=['legs', 'toes'])
    assert r'^frogs/(?P<pk>{})/l/e/g/s/$'.format(
        UUID_PATT) == get_member_targeting_regex(
            'frogs', UUID_PATT, modifiers='legs')
    with pytest.raises(TypeError):
        get_member_targeting_regex('frogs', UUID_PATT, modifiers=1)


def test_standard_routes():
    """Test that standard REST ``Route()``s are yielded from the aptly-named
    func.
    """
    api = API(api_version='0.1.0', service_name='Elements')
    class Skies(Resources):
        pass
    cr, dr, er, ir, nr, sr, ur = api.yield_standard_routes('sky', Skies)

    # POST /skies/
    assert cr.regex == '^skies/$'
    assert cr.name == 'skies'
    assert cr.http_method == 'POST'
    assert cr.resource_cls == Skies
    assert cr.method_name == 'create'

    # DELETE /skies/<UUID>/
    assert dr.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert dr.name == 'sky'
    assert dr.http_method == 'DELETE'
    assert dr.resource_cls == Skies
    assert dr.method_name == 'delete'

    # GET /skies/<UUID>/edit/
    assert er.regex == r'^skies/(?P<pk>{})/edit/$'.format(UUID_PATT)
    assert er.name == 'sky_edit'
    assert er.http_method == 'GET'
    assert er.resource_cls == Skies
    assert er.method_name == 'edit'

    # GET /skies/
    assert ir.regex == '^skies/$'
    assert ir.name == 'skies'
    assert ir.http_method == 'GET'
    assert ir.resource_cls == Skies
    assert ir.method_name == 'index'

    # GET /skies/new
    assert nr.regex == '^skies/new/$'
    assert nr.name == 'skies_new'
    assert nr.http_method == 'GET'
    assert nr.resource_cls == Skies
    assert nr.method_name == 'new'

    # GET /skies/<UUID>/
    assert sr.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert sr.name == 'sky'
    assert sr.http_method == 'GET'
    assert sr.resource_cls == Skies
    assert sr.method_name == 'show'

    # PUT /skies/<UUID>/
    assert ur.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert ur.name == 'sky'
    assert ur.http_method == 'PUT'
    assert ur.resource_cls == Skies
    assert ur.method_name == 'update'


def test_search_routes():
    """Test that search-related ``Route()``s are yielded from the aptly-named
    func.
    """
    api = API(api_version='0.1.0', service_name='Animals')
    class Octopodes(Resources):
        pass
    r1, r2, r3 = api.yield_search_routes('octopus', Octopodes)

    # SEARCH /octopodes/
    assert r1.regex == '^octopodes/$'
    assert r1.name == 'octopodes'
    assert r1.http_method == 'SEARCH'
    assert r1.resource_cls == Octopodes
    assert r1.method_name == 'search'

    # POST /octopodes/search/
    assert r2.regex == '^octopodes/search/$'
    assert r2.name == 'octopodes_search'
    assert r2.http_method == 'POST'
    assert r2.resource_cls == Octopodes
    assert r2.method_name == 'search'

    # GET /octopodes/new_search/
    assert r3.regex == '^octopodes/new_search/$'
    assert r3.name == 'octopodes_new_search'
    assert r3.http_method == 'GET'
    assert r3.resource_cls == Octopodes
    assert r3.method_name == 'new_search'
