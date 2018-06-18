"""Location Resources for Version Beta of the Storage Service API.

Defines ``Locations`` (a sub-class of ``remple.Resources``) in order to expose
CRUD operations on locations. Also includes custom endpoints for the following
operations:

- browse

"""

from __future__ import absolute_import
import base64
from collections import OrderedDict
import logging
import os

from locations.api.beta.remple import (
    CustomEndPoint,
    Resources,
    OK_STATUS,
    NOT_FOUND_STATUS,
    UNAUTHORIZED_MSG,
    FORBIDDEN_STATUS,
    get_error_schema_path,
    get_ref_response,
    schema_name2path,
)

from locations.api.beta.schemata import LocationSchema
from locations.models import Location

logger = logging.getLogger(__name__)


LOCATION_BROWSE_SCHEMA_NAME = 'LocationBrowseSchema'
LOCATION_BROWSE_SCHEMA = OrderedDict([
    ('type', 'object'),
    ('properties', OrderedDict([
        ('entries', OrderedDict([
            ('type', 'array'),
            ('items', {'type': 'string', 'format': 'byte'}),
        ])),
        ('directories', OrderedDict([
            ('type', 'array'),
            ('items', {'type': 'string', 'format': 'byte'}),
        ])),
        ('properties', {'type': 'object'}),
    ])),
    ('required', ['entries', 'directories', 'properties']),
])

LOCATION_BROWSE_PARAMS = [
    OrderedDict([
        ('name', 'pk'),
        ('in', 'path'),
        ('description', 'UUID of the location to browse'),
        ('required', True),
        ('schema', OrderedDict([
            ('type', 'string'),
            ('format', 'UUID of a Location resource'),
        ])),
    ]),
    OrderedDict([
        ('name', 'path'),
        ('in', 'query'),
        ('default', ''),
        ('description', 'Path to browse within the Location (optional)'),
        ('schema', {'type': 'string'}),
    ]),
]

LOCATION_BROWSE_RESPONSES = OrderedDict([
    ('200', get_ref_response(
        description='Request to browse a location was successful',
        ref=schema_name2path(LOCATION_BROWSE_SCHEMA_NAME))),
    ('404', get_ref_response(
        description='Request to browse a location failed because there is no'
                    ' location resource with the specified pk.',
        ref=get_error_schema_path())),
    ('403', get_ref_response(
        description='Request to browse location failed because the user is'
                    ' forbidden from viewing this location.',
        ref=get_error_schema_path())),
])


class Locations(Resources):
    model_cls = Location
    schema_cls = LocationSchema

    # Custom endpoints
    browse = CustomEndPoint(
        action='browse',  # will contribute to operationId=locations.browse
        path='{pk}/browse/',
        http_method='get',
        method_name='browse_method',
        tags=['locations'],
        summary='Browse a location',
        description='Browse a location at the root (default) or at a supplied'
                    ' path.',
        parameters=LOCATION_BROWSE_PARAMS,
        responses=LOCATION_BROWSE_RESPONSES,
        schemata={LOCATION_BROWSE_SCHEMA_NAME: LOCATION_BROWSE_SCHEMA})

    def browse_method(self, pk):
        """Handler for a GET /locations/<pk>/browse/ request.
        :param str pk (in: path): the UUID value of the resource to be returned.
        :param str path (in: query params): the (optional) path to browse the
            location at.
        :returns: a dict with keys for 'entries', 'directories', and
            'properties'.
        """
        logger.info('Attempting to browse a %s', self.hmn_member_name)
        location_mdl = self._model_from_pk(pk)
        if not location_mdl:
            msg = self._rsrc_not_exist(pk)
            logger.warning(msg)
            return {'error': msg}, NOT_FOUND_STATUS
        if self._model_access_unauth(location_mdl) is not False:
            logger.warning(UNAUTHORIZED_MSG)
            return UNAUTHORIZED_MSG, FORBIDDEN_STATUS

        # TODO remove duplication from api/resources.py
        path = self.request.GET.get('path', '')
        location_path = location_mdl.full_path
        if isinstance(location_path, unicode):
            location_path = location_path.encode('utf8')
        if not path.startswith(location_path):
            path = os.path.join(location_path, path)
        # TODO remove duplication from api/v2.py
        objects = location_mdl.space.browse(path)
        objects['entries'] = map(base64.b64encode, objects['entries'])
        objects['directories'] = map(base64.b64encode, objects['directories'])
        objects['properties'] = {base64.b64encode(k): v for k, v in
                                 objects.get('properties', {}).items()}
        return objects, OK_STATUS
