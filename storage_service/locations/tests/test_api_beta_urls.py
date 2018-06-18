# -*- coding: utf8 -*-
"""Tests for the api.beta.urls module."""

from __future__ import print_function

import pytest

from locations.api.beta.remple import (
    API,
    UUID_PATT,
    ID_PATT,
    get_collection_targeting_regex,
    get_member_targeting_regex,
    Resources,
)
from locations.api.beta.resources import (
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
    api_v_slug = 'v0_1'
    expecteds = (
        ('{}_location'.format(api_v_slug), '^locations/(?P<pk>{})/$'.format(UUID_PATT)),
        ('{}_location_edit'.format(api_v_slug),
         '^locations/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('{}_locations'.format(api_v_slug), '^locations/$'),
        ('{}_locations_new'.format(api_v_slug), '^locations/new/$'),
        ('{}_locations_new_search'.format(api_v_slug), '^locations/new_search/$'),
        ('{}_locations_search'.format(api_v_slug), '^locations/search/$'),
        # Note the ID_PATT for /packages/ because of pk_patt above
        ('{}_package'.format(api_v_slug), '^packages/(?P<pk>{})/$'.format(ID_PATT)),
        ('{}_package_edit'.format(api_v_slug),
         '^packages/(?P<pk>{})/edit/$'.format(ID_PATT)),
        ('{}_packages'.format(api_v_slug), '^packages/$'),
        ('{}_packages_new'.format(api_v_slug), '^packages/new/$'),
        ('{}_packages_new_search'.format(api_v_slug), '^packages/new_search/$'),
        ('{}_packages_search'.format(api_v_slug), '^packages/search/$'),
        ('{}_pipeline'.format(api_v_slug), '^pipelines/(?P<pk>{})/$'.format(UUID_PATT)),
        ('{}_pipeline_edit'.format(api_v_slug),
         '^pipelines/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('{}_pipelines'.format(api_v_slug), '^pipelines/$'),
        ('{}_pipelines_new'.format(api_v_slug), '^pipelines/new/$'),
        ('{}_pipelines_new_search'.format(api_v_slug), '^pipelines/new_search/$'),
        ('{}_pipelines_search'.format(api_v_slug), '^pipelines/search/$'),
        # Note that the /spaces/ resource has no search-related routes.
        ('{}_space'.format(api_v_slug), '^spaces/(?P<pk>{})/$'.format(UUID_PATT)),
        ('{}_space_edit'.format(api_v_slug), '^spaces/(?P<pk>{})/edit/$'.format(UUID_PATT)),
        ('{}_spaces'.format(api_v_slug), '^spaces/$'),
        ('{}_spaces_new'.format(api_v_slug), '^spaces/new/$'),
        ('{}_schema'.format(api_v_slug), r'^$'),
        ('{}_yaml'.format(api_v_slug), r'^yaml/$'),
        ('{}_doc'.format(api_v_slug), r'^doc/$'),
        ('{}_client'.format(api_v_slug), r'^client/$'),
    )
    for expected in expecteds:
        assert expected in urlpatterns_names_regexes

    # Make assertions about ``api.routes``
    assert api.routes[r'^locations/$'] == {
        'http_methods': {'GET': (Locations, 'index'),
                         'POST': (Locations, 'create'),
                         'SEARCH': (Locations, 'search')},
        'route_name': '{}_locations'.format(api_v_slug)}
    assert api.routes[
        r'^locations/(?P<pk>{})/$'.format(UUID_PATT)] == {
        'http_methods': {'DELETE': (Locations, 'delete'),
                         'GET': (Locations, 'show'),
                         'PUT': (Locations, 'update')},
        'route_name': '{}_location'.format(api_v_slug)}
    assert api.routes[
        r'^locations/(?P<pk>{})/edit/$'.format(UUID_PATT)] == {
        'http_methods': {'GET': (Locations, 'edit')},
        'route_name': '{}_location_edit'.format(api_v_slug)}
    assert api.routes['^locations/new/$'] == {
        'http_methods': {'GET': (Locations, 'new')},
        'route_name': '{}_locations_new'.format(api_v_slug)}
    assert api.routes['^locations/new_search/$'] == {
        'http_methods': {'GET': (Locations, 'new_search')},
        'route_name': '{}_locations_new_search'.format(api_v_slug)}
    assert api.routes['^locations/search/$'] == {
        'http_methods': {'POST': (Locations, 'search')},
        'route_name': '{}_locations_search'.format(api_v_slug)}
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
    assert cr.name == 'v0_1_skies'
    assert cr.http_method == 'POST'
    assert cr.resource_cls == Skies
    assert cr.method_name == 'create'

    # DELETE /skies/<UUID>/
    assert dr.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert dr.name == 'v0_1_sky'
    assert dr.http_method == 'DELETE'
    assert dr.resource_cls == Skies
    assert dr.method_name == 'delete'

    # GET /skies/<UUID>/edit/
    assert er.regex == r'^skies/(?P<pk>{})/edit/$'.format(UUID_PATT)
    assert er.name == 'v0_1_sky_edit'
    assert er.http_method == 'GET'
    assert er.resource_cls == Skies
    assert er.method_name == 'edit'

    # GET /skies/
    assert ir.regex == '^skies/$'
    assert ir.name == 'v0_1_skies'
    assert ir.http_method == 'GET'
    assert ir.resource_cls == Skies
    assert ir.method_name == 'index'

    # GET /skies/new
    assert nr.regex == '^skies/new/$'
    assert nr.name == 'v0_1_skies_new'
    assert nr.http_method == 'GET'
    assert nr.resource_cls == Skies
    assert nr.method_name == 'new'

    # GET /skies/<UUID>/
    assert sr.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert sr.name == 'v0_1_sky'
    assert sr.http_method == 'GET'
    assert sr.resource_cls == Skies
    assert sr.method_name == 'show'

    # PUT /skies/<UUID>/
    assert ur.regex == r'^skies/(?P<pk>{})/$'.format(UUID_PATT)
    assert ur.name == 'v0_1_sky'
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
    assert r1.name == 'v0_1_octopodes'
    assert r1.http_method == 'SEARCH'
    assert r1.resource_cls == Octopodes
    assert r1.method_name == 'search'

    # POST /octopodes/search/
    assert r2.regex == '^octopodes/search/$'
    assert r2.name == 'v0_1_octopodes_search'
    assert r2.http_method == 'POST'
    assert r2.resource_cls == Octopodes
    assert r2.method_name == 'search'

    # GET /octopodes/new_search/
    assert r3.regex == '^octopodes/new_search/$'
    assert r3.name == 'v0_1_octopodes_new_search'
    assert r3.http_method == 'GET'
    assert r3.resource_cls == Octopodes
    assert r3.method_name == 'new_search'
