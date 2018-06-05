"""Version 3 of the Storage Service API.

The Storage Service exposes the following resources via a consistent HTTP JSON
interface under the path namespace /api/v3/:

- /locations/ --- purpose-specific paths within a /spaces/ resource
- /packages/ --- Information Package (SIP, DIP or AIP)
- /spaces/ --- storage space with behaviour specific to backing system
- /pipelines/ --- an Archivematica instance that is the source of a package

The following resources may be exposed later:

- /file/ --- a file on disk (which is in a package), represented as db row.
- /fsobjects/ --- directories and files on disk, read-only, no database models

All resources have endpoints that follow this pattern::

    +-----------------+-------------+----------------------------+------------+
    | Purpose         | HTTP Method | Path                       | Method     |
    +-----------------+-------------+----------------------------+------------+
    | Create new      | POST        | /<cllctn_name>/            | create     |
    | Create data     | GET         | /<cllctn_name>/new/        | new        |
    | Read all        | GET         | /<cllctn_name>/            | index      |
    | Read specific   | GET         | /<cllctn_name>/<id>/       | show       |
    | Update specific | PUT         | /<cllctn_name>/<id>/       | update     |
    | Update data     | GET         | /<cllctn_name>/<id>/edit/  | edit       |
    | Delete specific | DELETE      | /<cllctn_name>/<id>/       | delete     |
    | Search          | SEARCH      | /<cllctn_name>/            | search     |
    | Search          | POST        | /<cllctn_name>/search/     | search     |
    | Search data     | GET         | /<cllctn_name>/new_search/ | new_search |
    +-----------------+-------------+----------------------------+------------+

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

from locations.api.v3.remple import API
from locations.api.v3.resources import (
    Locations,
    Packages,
    Spaces,
    Pipelines,
)

API_VERSION = '3.0.0'
SERVICE_NAME = 'Archivematica Storage Service'

resources = {
    'location': {'resource_cls': Locations},
    'package': {'resource_cls': Packages},  # Readonly because of super-class of ``Packages``
    'space': {'resource_cls': Spaces},
    'pipeline': {'resource_cls': Pipelines},
}

api = API(api_version=API_VERSION, service_name=SERVICE_NAME)
api.register_resources(resources)
urls = api.get_urlpatterns()

__all__ = ('urls', 'api')
