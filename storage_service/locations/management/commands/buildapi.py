# -*- coding: utf-8 -*-

"""Management command that builds the OpenAPI YAML for the Storage Service's
REST API.

It also builds a Python client module that contains the YAML and which
dynamically defines a REST API client.

To run from a Docker Compose deploy::

    $ docker-compose exec archivematica-storage-service /src/storage_service/manage.py buildapi
    OpenAPI specification written. See:

    - spec file: /src/storage_service/static/openapi/openapispecs/storage-service-0.11.0-openapi-3.0.0.yml
    - client Python script: /src/storage_service/static/openapi/openapispecs/client.py

After the above is run, it should be possible to view the Swagger-UI at
static/openapi/index.html.

The YAML spec file should be downloadable at the path
static/openapi/openapispecs/storage-service-0.11.0-openapi-3.0.0.yml.

Finally, the Python client script for interacting with the API should be
downloadable at the path static/openapi/openapispecs/client.py. See the
docstring of the generated clien.py file for usage or do the following::

    >>> from client import client_class
    >>> help(client_class)

TODOs:

- Add CI script (similar to Django checkformigrations) that checks whether the
  OpenAPI spec needs to be rebuilt.

  - Relatedly, make sure all dicts are ordered dicts so that we don't get
    spurious diffs between semantically equivalent specs.
"""

import os
import pprint
import yaml

import django
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand

from locations.api.v3 import api
from storage_service import __version__ as ss_version


def _get_client_builder_path():
    return os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        'locations',
        'api',
        'v3',
        'remple',
        'clientbuilder.py',
    )


def _get_spec_dir_path():
    return os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        'static',
        'openapi',
        'openapispecs',
    )


def build_client_script(open_api_dict):
    client_builder_path = _get_client_builder_path()
    spec_dir_path = _get_spec_dir_path()
    client_path = os.path.join(spec_dir_path, 'client.py')
    with open(client_path, 'w') as fileo:
        with open(client_builder_path) as filei:
            for line in filei:
                if line.startswith('# OPENAPI_SPEC goes here'):
                    fileo.write('\n\nOPENAPI_SPEC = (\n{}\n)\n\n'.format(
                        pprint.pformat(open_api_dict)))
                else:
                    fileo.write(line)
    return client_path


def main(output_type='yaml'):
    open_api_spec = api.generate_open_api_spec()
    spec_dir_path = _get_spec_dir_path()
    if output_type == 'yaml':
        open_api = api.to_yaml(open_api_spec)
    else:
        open_api = api.to_json(open_api_spec)
    write_name = 'storage-service-{}-openapi-{}.{}'.format(
        ss_version, open_api_spec['info']['version'],
        {'yaml': 'yml'}.get(output_type, output_type))
    write_path = os.path.join(spec_dir_path, write_name)
    with open(write_path, 'w') as fi:
        fi.write(open_api)
    client_path = build_client_script(open_api_spec)
    print('OpenAPI specification written. See:\n\n'
          '- spec file: {}\n'
          '- client Python script: {}'.format(write_path, client_path))
    return 0


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '-o',
            '--output-type',
            default='yaml',
            type=str,
            dest='output_type',
            help='Output type for the API Spec: yaml or json',
        )

    def handle(self, *args, **options):
        output_type = options['output_type'].strip().lower()
        if output_type not in ('json', 'yaml'):
            output_type = 'yaml'
        main(output_type=output_type)
