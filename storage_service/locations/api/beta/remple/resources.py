"""Remple Resources

Defines the following classes for easily creating controller sub-classes that
handle requests to REST resources:

- ``Resources``
- ``ReadonlyResources``
"""

from __future__ import absolute_import

from collections import namedtuple
from functools import partial
import json
import logging

from django.db import OperationalError
from django.db.models.fields.related import ManyToManyField, ForeignKey
from formencode.validators import Invalid, UnicodeString
from formencode.foreach import ForEach
import inflect

from .constants import (
    BAD_REQUEST_STATUS,
    FORBIDDEN_STATUS,
    JSONDecodeErrorResponse,
    NOT_FOUND_STATUS,
    CREATED_STATUS,
    OK_STATUS,
    READONLY_RSLT,
    UNAUTHORIZED_MSG,
)
from .querybuilder import QueryBuilder, SearchParseError
from .schemata import PaginatorSchema, ResourceURI
from .utils import normalize


logger = logging.getLogger(__name__)


class ReadonlyResources(object):
    """Super-class of ``Resources`` and all read-only resource views.

    +-----------------+-------------+--------------------------+--------+
    | Purpose         | HTTP Method | Path                     | Method |
    +=================+=============+==========================+========+
    | Create new      | POST        | /<cllctn_name>           | create |
    +-----------------+-------------+--------------------------+--------+
    | Create data     | GET         | /<cllctn_name>/new       | new    |
    +-----------------+-------------+--------------------------+--------+
    | Read all        | GET         | /<cllctn_name>           | index  |
    +-----------------+-------------+--------------------------+--------+
    | Read specific   | GET         | /<cllctn_name>/<pk>      | show   |
    +-----------------+-------------+--------------------------+--------+
    | Update specific | PUT         | /<cllctn_name>/<pk>      | update |
    +-----------------+-------------+--------------------------+--------+
    | Update data     | GET         | /<cllctn_name>/<pk>/edit | edit   |
    +-----------------+-------------+--------------------------+--------+
    | Delete specific | DELETE      | /<cllctn_name>/<pk>      | delete |
    +-----------------+-------------+--------------------------+--------+
    | Search          | SEARCH      | /<cllctn_name>           | search |
    +-----------------+-------------+--------------------------+--------+

    Note: the create, new, update, edit, and delete actions are all exposed via
    the REST API; however, they invariably return 404 responses.
    """

    primary_key = 'uuid'
    _query_builder = None

    inflect_p = inflect.engine()
    inflect_p.classical()

    def __init__(self, request, server_path='/api/0_1_0/', other_resources=None):
        self.request = request
        self.server_path = server_path
        self.other_resources = other_resources or []
        self._logged_in_user = None
        self._query_builder = None
        # Names
        if not getattr(self, 'collection_name', None):
            self.collection_name = self.__class__.__name__.lower()
        if not getattr(self, 'hmn_collection_name', None):
            self.hmn_collection_name = self.collection_name
        if not getattr(self, 'member_name', None):
            self.member_name = self.inflect_p.singular_noun(
                self.collection_name)
        if not getattr(self, 'hmn_member_name', None):
            self.hmn_member_name = self.member_name

    # RsrcColl is a resource collection object factory. Each instance holds the
    # relevant model name and instance getter for a given resource collection
    # name.
    RsrcColl = namedtuple('RsrcColl', ['model_cls', 'getter'])

    @staticmethod
    def get_mini_dicts_getter(model_cls):
        def func():
            return [mi.get_mini_dict() for mi in model_cls.objects.all()]
        return func

    @property
    def query_builder(self):
        return self._get_query_builder()

    @classmethod
    def _get_query_builder(cls):
        if not cls._query_builder:
            cls._query_builder = QueryBuilder(
                cls.model_cls,
                primary_key=cls.primary_key)
        return cls._query_builder

    @property
    def logged_in_user(self):
        """Property to access the logged in user. QUESTION: Is this a db
        model?
        """
        if not self._logged_in_user:
            self._logged_in_user = self.request.user
        return self._logged_in_user

    ###########################################################################
    # Public CRUD(S) Methods
    ###########################################################################

    def create(self):
        logger.warning('Failed attempt to create a read-only %s',
                       self.hmn_member_name)
        return READONLY_RSLT, NOT_FOUND_STATUS

    def new(self):
        logger.warning('Failed attempt to get data for creating a read-only %s',
                       self.hmn_member_name)
        return READONLY_RSLT, NOT_FOUND_STATUS

    def index(self):
        """Get all resources.

        - URL: ``GET /<resource_collection_name>`` with optional query string
          parameters for ordering and pagination.

        :returns: a JSON-serialized array of resources objects.
        """
        logger.info('Attempting to read all %s', self.hmn_collection_name)
        query_set = self.model_cls.objects
        get_params = dict(self.request.GET)
        try:
            query_set = self.add_order_by(query_set, get_params)
            query_set = self._filter_query(query_set)
            result = self.add_pagination(query_set, get_params)
        except Invalid as error:
            errors = error.unpack_errors()
            logger.warning('Attempt to read all %s resulted in an error(s): %s',
                           self.hmn_collection_name, errors)
            return {'error': errors}, BAD_REQUEST_STATUS
        headers_ctl = self._headers_control(result)
        if headers_ctl is not False:
            return headers_ctl
        logger.info('Read all %s', self.hmn_collection_name)
        return result, OK_STATUS

    def show(self, pk):
        """Return a resource, given its pk.
        :URL: ``GET /<resource_collection_name>/<pk>``
        :param str pk: the ``pk`` value of the resource to be returned.
        :returns: a resource model object.
        """
        logger.info('Attempting to read a single %s', self.hmn_member_name)
        resource_model = self._model_from_pk(pk)
        if not resource_model:
            msg = self._rsrc_not_exist(pk)
            logger.warning(msg)
            return {'error': msg}, NOT_FOUND_STATUS
        if self._model_access_unauth(resource_model) is not False:
            logger.warning(UNAUTHORIZED_MSG)
            return UNAUTHORIZED_MSG, FORBIDDEN_STATUS
        logger.info('Read a single %s', self.hmn_member_name)
        return self._get_show_dict(resource_model), OK_STATUS

    def update(self, pk):
        logger.warning('Failed attempt to update a read-only %s',
                       self.hmn_member_name)
        return READONLY_RSLT, NOT_FOUND_STATUS

    def edit(self, pk):
        logger.warning('Failed attempt to get data for updating a read-only %s',
                       self.hmn_member_name)
        return READONLY_RSLT, NOT_FOUND_STATUS

    def delete(self, pk):
        logger.warning('Failed attempt to delete a read-only %s',
                       self.hmn_member_name)
        return READONLY_RSLT, NOT_FOUND_STATUS

    def search(self):
        """Return the list of resources matching the input JSON query.

        - URL: ``SEARCH /<resource_collection_name>`` (or
               ``POST /<resource_collection_name>/search``)
        - request body: A JSON object of the form::

              {"query": {"filter": [ ... ], "order_by": [ ... ]},
               "paginator": { ... }}

          where the ``order_by`` and ``paginator`` attributes are optional.
        """
        logger.info('Attempting to search over %s', self.hmn_collection_name)
        try:
            python_search_params = json.loads(
                self.request.body.decode('utf8'))
        except ValueError:
            logger.warning('Request body was not valid JSON')
            logger.info(self.request.body.decode('utf8'))
            return JSONDecodeErrorResponse, BAD_REQUEST_STATUS
        try:
            query_set = self.query_builder.get_query_set(
                python_search_params.get('query'))
        except (SearchParseError, Invalid) as error:
            errors = error.unpack_errors()
            logger.warning(
                'Attempt to search over all %s resulted in an error(s): %s',
                self.hmn_collection_name, errors, exc_info=True)
            return {'error': errors}, BAD_REQUEST_STATUS
        # Might be better to catch (OperationalError, AttributeError,
        # InvalidRequestError, RuntimeError):
        except Exception as error:  # FIX: too general exception
            logger.warning('Filter expression (%s) raised an unexpected'
                           ' exception: %s.', self.request.body, error)
            return {'error': 'The specified search parameters generated an'
                             ' invalid database query'}, BAD_REQUEST_STATUS
        query_set = self._eagerload_model(query_set)
        query_set = self._filter_query(query_set)
        try:
            ret = self.add_pagination(
                query_set, python_search_params.get('paginator'))
        except OperationalError:
            msg = ('The specified search parameters generated an invalid'
                   ' database query')
            logger.warning(msg)
            return {'error': msg}, BAD_REQUEST_STATUS
        except Invalid as error:  # For paginator schema errors.
            errors = error.unpack_errors()
            logger.warning(
                'Attempt to search over all %s resulted in an error(s): %s',
                self.hmn_collection_name, errors)
            return {'error': errors}, BAD_REQUEST_STATUS
        else:
            logger.info('Successful search over %s', self.hmn_collection_name)
            return ret, OK_STATUS

    def new_search(self):
        """Return the data necessary to search over this type of resource.

        - URL: ``GET /<resource_collection_name>/new_search``

        :returns: a JSON object with a ``search_parameters`` attribute which
         resolves to an object with attributes ``attributes`` and ``relations``.
        """
        logger.info('Returning search parameters for %s', self.hmn_member_name)
        return {'search_parameters':
                self.query_builder.get_search_parameters()}, OK_STATUS

    def get_paginated_query_results(self, query_set, paginator):
        if 'count' not in paginator:
            paginator['count'] = query_set.count()
        start, end = _get_start_and_end_from_paginator(paginator)
        return {
            'paginator': paginator,
            'items': [self._get_show_dict(rsrc_mdl) for rsrc_mdl in
                      query_set[start:end]]
        }

    def add_pagination_OLD(self, query_set, paginator):
        if (paginator and paginator.get('page') is not None and
                paginator.get('items_per_page') is not None):
            # raises formencode.Invalid if paginator is invalid
            paginator = PaginatorSchema.to_python(paginator)
            return self.get_paginated_query_results(query_set, paginator)
        return [self._get_show_dict(rsrc_mdl) for rsrc_mdl in query_set]

    def add_pagination(self, query_set, paginator):
        paginator = paginator or {}
        try:
            page = int(paginator.get('page', [1])[0])
        except TypeError:
            page = int(paginator.get('page', [1]))
        try:
            items_per_page = int(paginator.get('items_per_page', [50])[0])
        except TypeError:
            items_per_page = int(paginator.get('items_per_page', [50]))
        new_paginator = {
            'page': page,
            'items_per_page': items_per_page,
        }
        paginator = PaginatorSchema.to_python(new_paginator)
        return self.get_paginated_query_results(query_set, paginator)

    ###########################################################################
    # Private Methods for Override: redefine in views for custom behaviour
    ###########################################################################

    def _get_show_dict(self, resource_model):
        """Return the model as a dict for the return value of a successful show
        request. This is indirected so that resources like collections can
        override and do special things.
        """
        try:
            return resource_model.get_dict()
        except AttributeError:
            return self.to_dict(resource_model)

    def _get_create_dict(self, resource_model):
        return self._get_show_dict(resource_model)

    def _get_edit_dict(self, resource_model):
        return self._get_show_dict(resource_model)

    def _get_update_dict(self, resource_model):
        return self._get_create_dict(resource_model)

    def _eagerload_model(self, query_set):
        """Override this in a subclass with model-specific eager loading."""
        return get_eagerloader(self.model_cls)(query_set)

    def _filter_query(self, query_set):
        """Override this in a subclass with model-specific query filtering.
        E.g.,::

            >>> return filter_restricted_models(self.model_cls, query_set)
        """
        return query_set

    def _headers_control(self, result):
        """Take actions based on header values and/or modify headers. If
        something other than ``False`` is returned, that will be the response.
        Useful for Last-Modified/If-Modified-Since caching, e.g., in ``index``
        method of Forms view.
        """
        return False

    def _update_unauth(self, resource_model):
        """Return ``True`` if update of the resource model cannot proceed."""
        return self._model_access_unauth(resource_model)

    def _update_unauth_msg_obj(self):
        """Return the dict that will be returned when ``self._update_unauth()``
        returns ``True``.
        """
        return UNAUTHORIZED_MSG

    def _model_access_unauth(self, resource_model):
        """Implement resource/model-specific access controls based on
        (un-)restricted(-ness) of the current logged in user and the resource
        in question. Return something other than ``False`` to trigger a 403
        response.
        """
        return False

    def _model_from_pk(self, pk):
        """Return a particular model instance, given the model pk."""
        try:
            return self.model_cls.objects.get(**{self.primary_key: pk})
        except (self.model_cls.DoesNotExist,
                self.model_cls.MultipleObjectsReturned):
            return None

    ###########################################################################
    # Utilities
    ###########################################################################

    def _rsrc_not_exist(self, pk):
        return 'There is no %s with %s %s' % (self.hmn_member_name,
                                              self.primary_key, pk)

    def add_order_by(self, query_set, order_by_params, query_builder=None):
        """Add an ORDER BY clause to the query_set using the ``get_order_bys``
        method of the instance's query_builder (if possible) or using a default
        ORDER BY <self.primary_key> ASC.
        """
        if not query_builder:
            query_builder = self.query_builder
        inp_order_bys = None
        inp_order_by = list(filter(
            None, [order_by_params.get('order_by_attribute', [None])[0],
                   order_by_params.get('order_by_subattribute', [None])[0],
                   order_by_params.get('order_by_direction', [None])[0]]))
        if inp_order_by:
            inp_order_bys = [inp_order_by]
        order_by = query_builder.get_order_bys(
            inp_order_bys, primary_key=self.primary_key)
        logger.info('Adding this order_by: "%s"', order_by)
        return query_set.order_by(*order_by)

    @staticmethod
    def get_resource_uri(server_path, collection_name, primary_key):
        return '{server_path}/{collection_name}/{primary_key}/'.format(
            server_path=server_path,
            collection_name=collection_name,
            primary_key=primary_key)

    @staticmethod
    def resource_uri2primary_key(resource_uri):
        return filter(None, resource_uri.split('/'))[-1]

    def inst2rsrc_uri(self, related_instance):
        related_primary_key = related_instance.pk
        related_rsrc_name = related_instance.__class__.__name__.lower()
        related_coll_name = self.inflect_p.plural(related_rsrc_name)
        related_rsrc_cls = self.other_resources.get(
            related_rsrc_name, {}).get('resource_cls')
        if related_rsrc_cls:
            related_primary_key = getattr(
                related_instance, related_rsrc_cls.primary_key)
        return self.get_resource_uri(
            self.server_path, related_coll_name,
            related_primary_key)

    def to_dict(self, instance):
        opts = instance._meta
        data = {'resource_uri': self.get_resource_uri(
            self.server_path, self.collection_name,
            getattr(instance, self.primary_key))}
        for f in opts.concrete_fields + opts.many_to_many:
            if isinstance(f, ManyToManyField):
                if instance.pk is None:
                    data[f.name] = []
                else:
                    data[f.name] = [
                        self.inst2rsrc_uri(related_instance)
                        for related_instance
                        in f.value_from_object(instance)]
            elif isinstance(f, ForeignKey):
                data[f.name] = f.value_from_object(instance)
                val = None
                related_instance = getattr(instance, f.name, None)
                if related_instance:
                    val = self.inst2rsrc_uri(related_instance)
                data[f.name] = val
            else:
                data[f.name] = f.value_from_object(instance)
        return data


class Resources(ReadonlyResources):
    """Abstract base class for all (modifiable) resource views. RESTful
    CRUD(S) interface:

    +-----------------+-------------+--------------------------+--------+
    | Purpose         | HTTP Method | Path                     | Method |
    +-----------------+-------------+--------------------------+--------+
    | Create new      | POST        | /<cllctn_name>           | create |
    | Create data     | GET         | /<cllctn_name>/new       | new    |
    | Read all        | GET         | /<cllctn_name>           | index  |
    | Read specific   | GET         | /<cllctn_name>/<pk>      | show   |
    | Update specific | PUT         | /<cllctn_name>/<pk>      | update |
    | Update data     | GET         | /<cllctn_name>/<pk>/edit | edit   |
    | Delete specific | DELETE      | /<cllctn_name>/<pk>      | delete |
    | Search          | SEARCH      | /<cllctn_name>           | search |
    +-----------------+-------------+--------------------------+--------+
    """

    @classmethod
    def get_create_schema_cls(cls):
        return getattr(cls, 'schema_create_cls', getattr(cls, 'schema_cls', None))

    @classmethod
    def get_update_schema_cls(cls):
        return getattr(cls, 'schema_update_cls', getattr(cls, 'schema_cls', None))

    def preprocess_user_data(self, validated_user_data, schema):
        """Process the user-provided and validated ``validated_user_data``
        dict, crucially returning a *new* dict created from it which is ready
        for construction of a model instance.
        """
        processed_data = {}
        schema_cls = schema.__class__
        for field_name, field in schema_cls.fields.items():
            value = validated_user_data[field_name]
            if isinstance(field, ForEach) and isinstance(
                    field.validators[0], ResourceURI):
                processed_data[field_name] = value
            elif isinstance(field, UnicodeString):
                processed_data[field_name] = normalize(value)
            else:
                processed_data[field_name] = value
        return processed_data

    ###########################################################################
    # Public CRUD(S) Methods
    ###########################################################################

    def create(self):
        """Create a new resource and return it.
        :URL: ``POST /<resource_collection_name>``
        :request body: JSON object representing the resource to create.
        :returns: the newly created resource.
        """
        logger.info('Attempting to create a new %s.', self.hmn_member_name)
        schema_cls = self.get_create_schema_cls()
        schema = schema_cls()
        try:
            user_data = json.loads(self.request.body.decode('utf8'))
        except ValueError:
            logger.warning('Request body was not valid JSON')
            return JSONDecodeErrorResponse, BAD_REQUEST_STATUS
        state = self._get_create_state(user_data)
        try:
            validated_user_data = schema.to_python(user_data, state)
        except Invalid as error:
            errors = error.unpack_errors()
            logger.warning(
                'Attempt to create a(n) %s resulted in an error(s): %s',
                self.hmn_member_name, errors)
            return {'error': errors}, BAD_REQUEST_STATUS
        resource = self._create_new_resource(validated_user_data, schema)
        resource.save()
        self._post_create(resource)
        logger.info('Created a new %s.', self.hmn_member_name)
        return self._get_create_dict(resource), CREATED_STATUS

    def new(self):
        """Return the data necessary to create a new resource.

        - URL: ``GET /<resource_collection_name>/new/``.

        :returns: a dict containing the related resources necessary to create a
                  new resource of this type.

        .. note:: See :func:`_get_new_edit_data` to understand how the query
           string parameters can affect the contents of the lists in the
           returned dictionary.
        """
        logger.info('Returning the data needed to create a new %s.',
                    self.hmn_member_name)
        return self._get_new_edit_data(self.request.GET), OK_STATUS

    def update(self, pk):
        """Update a resource and return it.

        - URL: ``PUT /<resource_collection_name>/<pk>``
        - Request body: JSON object representing the resource with updated
          attribute values.

        :param str pk: the ``pk`` value of the resource to be updated.
        :returns: the updated resource model.
        """
        resource_model = self._model_from_pk(pk)
        logger.info('Attempting to update %s %s.', self.hmn_member_name, pk)
        if not resource_model:
            msg = self._rsrc_not_exist(pk)
            logger.warning(msg)
            return {'error': msg}, NOT_FOUND_STATUS
        if self._update_unauth(resource_model) is not False:
            msg = self._update_unauth_msg_obj()
            logger.warning(msg)
            return msg, FORBIDDEN_STATUS
        schema_cls = self.get_update_schema_cls()
        schema = schema_cls()
        try:
            values = json.loads(self.request.body.decode('utf8'))
        except ValueError:
            logger.warning(JSONDecodeErrorResponse)
            return JSONDecodeErrorResponse, BAD_REQUEST_STATUS
        state = self._get_update_state(values, pk, resource_model)
        try:
            validated_user_data = schema.to_python(values, state)
        except Invalid as error:
            errors = error.unpack_errors()
            logger.warning(errors)
            return {'error': errors}, BAD_REQUEST_STATUS
        resource_model = self._update_resource_model(
            resource_model, validated_user_data, schema)
        # resource_model will be False if there are no changes
        if not resource_model:
            msg = ('The update request failed because the submitted data were'
                   ' not new.')
            logger.warning(msg)
            return {'error': msg}, BAD_REQUEST_STATUS
        resource_model.save()
        self._post_update(resource_model)
        logger.info('Updated %s %s.', self.hmn_member_name, pk)
        return self._get_update_dict(resource_model), OK_STATUS

    def edit(self, pk):
        """Return a resource and the data needed to update it.
        :URL: ``GET /<resource_collection_name>/edit``
        :param str pk: the ``pk`` value of the resource that will be updated.
        :returns: a dictionary of the form::

                {"<resource_member_name>": {...}, "data": {...}}

            where the value of the ``<resource_member_name>`` key is a
            dictionary representation of the resource and the value of the
            ``data`` key is a dictionary containing the data needed to edit an
            existing resource of this type.
        """
        resource_model = self._model_from_pk(pk)
        logger.info('Attempting to return the data needed to update %s %s.',
                    self.hmn_member_name, pk)
        if not resource_model:
            msg = self._rsrc_not_exist(pk)
            logger.warning(msg)
            return {'error': msg}, NOT_FOUND_STATUS
        if self._model_access_unauth(resource_model) is not False:
            logger.warning('User not authorized to access edit action on model')
            return UNAUTHORIZED_MSG, FORBIDDEN_STATUS
        logger.info('Returned the data needed to update %s %s.',
                    self.hmn_member_name, pk)
        return {
            'data': self._get_new_edit_data(self.request.GET, mode='edit'),
            'resource': self._get_edit_dict(resource_model)
        }, OK_STATUS

    def delete(self, pk):
        """Delete an existing resource and return it.
        :URL: ``DELETE /<resource_collection_name>/<pk>``
        :param str pk: the ``pk`` value of the resource to be deleted.
        :returns: the deleted resource model.
        """
        resource_model = self._model_from_pk(pk)
        logger.info('Attempting to delete %s %s.', self.hmn_member_name, pk)
        if not resource_model:
            msg = self._rsrc_not_exist(pk)
            logger.warning(msg)
            return {'error': msg}, NOT_FOUND_STATUS
        if self._delete_unauth(resource_model) is not False:
            msg = self._delete_unauth_msg_obj()
            logger.warning(msg)
            return msg, FORBIDDEN_STATUS
        error_msg = self._delete_impossible(resource_model)
        if error_msg:
            logger.warning(error_msg)
            return {'error': error_msg}, FORBIDDEN_STATUS
        resource_dict = self._get_delete_dict(resource_model)
        self._pre_delete(resource_model)
        resource_model.delete()
        self._post_delete(resource_model)
        logger.info('Deleted %s %s.', self.hmn_member_name, pk)
        return resource_dict, OK_STATUS

    ###########################################################################
    # Private methods for write-able resources
    ###########################################################################

    def _delete_unauth(self, resource_model):
        """Implement resource/model-specific controls over delete requests.
        Return something other than ``False`` to trigger a 403 response.
        """
        return False

    def _delete_unauth_msg_obj(self):
        """Return the dict that will be returned when ``self._delete_unauth()``
        returns ``True``.
        """
        return UNAUTHORIZED_MSG

    def _get_delete_dict(self, resource_model):
        """Override this in sub-classes for special resource dict creation."""
        return self._get_show_dict(resource_model)

    def _pre_delete(self, resource_model):
        """Perform actions prior to deleting ``resource_model`` from the
        database.
        """
        pass

    def _post_delete(self, resource_model):
        """Perform actions after deleting ``resource_model`` from the
        database.
        """
        pass

    def _delete_impossible(self, resource_model):
        """Return something other than false in a sub-class if this particular
        resource model cannot be deleted.
        """
        return False

    def _create_new_resource(self, validated_user_data, schema):
        """Create a new resource.
        :param dict validated_user_data: the data for the resource to be
            created.
        :param formencode.Schema schema: schema object used to validate
            user-supplied data.
        :returns: an SQLAlchemy model object representing the resource.
        """
        data_from_user = self.preprocess_user_data(validated_user_data, schema)
        kwargs = {attr: val for attr, val in data_from_user.items()
                  if not isinstance(self.model_cls._meta.get_field(attr),
                                    ManyToManyField)}
        m2m = {attr: val for attr, val in data_from_user.items()
               if isinstance(self.model_cls._meta.get_field(attr),
                             ManyToManyField)}
        ret = self.model_cls(**kwargs)
        ret.save()
        for attr, vals in m2m.items():
            existing_val = getattr(ret, attr)
            through = getattr(existing_val, 'through', None)
            if through and (not through._meta.auto_created):
                this_attr = [f for f in through._meta.get_fields()
                             if isinstance(f, ForeignKey)][0].name
                for rltd_mdl in vals:
                    through.objects.get_or_create(
                        **{attr: rltd_mdl, this_attr: ret})
            else:
                for val in vals:
                    existing_val.add(val)
        return ret

    def _post_create(self, resource_model):
        """Perform some action after creating a new resource model in the
        database. E.g., with forms we have to update all of the forms that
        contain the newly entered form as a morpheme.
        """
        pass

    def _get_create_state(self, values):
        """Return a SchemaState instance for validation of the resource during
        a create request.
        """
        return SchemaState(
            full_dict=values,
            logged_in_user=self.logged_in_user)

    def _get_update_state(self, values, pk, resource_model):
        update_state = self._get_create_state(values)
        update_state.pk = pk
        return update_state

    def _update_resource_model(self, resource_model, validated_user_data,
                               schema):
        """Update the Django model instance ``resource_model`` with the dict
        ``validated_user_data`` and return something other than ``False`` if
        ``resource_model`` has changed as a result.
        :param resource_model: the resource model to be updated.
        :param dict validated_user_data: user-supplied representation of the
            updated resource.
        :param formencode.Schema schema: schema object used to validate
            user-supplied data.
        :returns: the updated resource model instance or ``False`` if the data
            did not result in an update of the model.
        """
        changed = False
        for attr, user_val in validated_user_data.items():
            if self._distinct(attr, resource_model, user_val):
                changed = True
                break
        if changed:
            for attr, user_val in self.preprocess_user_data(
                    validated_user_data, schema).items():
                existing_val = getattr(resource_model, attr)
                through = getattr(existing_val, 'through', None)
                if through and (not through._meta.auto_created):
                    this_attr = [f for f in through._meta.get_fields()
                                 if isinstance(f, ForeignKey)][0].name
                    for rltd_mdl in user_val:
                        through.objects.get_or_create(
                            **{attr: rltd_mdl, this_attr: resource_model})
                    to_delete = through.objects.filter(
                        **{this_attr: resource_model}).exclude(
                            **{'{}__in'.format(attr): user_val})
                    to_delete.delete()
                else:
                    setattr(resource_model, attr, user_val)
            return resource_model
        return changed

    def _distinct(self, attr, resource_model, new_val):
        """Return true if ``new_val`` is distinct from ``existing_val``. The
        ``attr`` value is provided so that certain attributes (e.g., m2m) can
        have a special definition of "distinct".
        """
        field = resource_model.__class__._meta.get_field(attr)
        existing_val = getattr(resource_model, attr)
        if isinstance(field, ManyToManyField):
            new_val = sorted(m.pk for m in new_val)
            existing_val = sorted(m.pk for m in existing_val.all())
        field = resource_model.__class__._meta.get_field(attr)
        return new_val != existing_val

    def _post_update(self, resource_model):
        """Perform some action after updating an existing resource model in the
        database.
        """
        pass

    def get_most_recent_modification_datetime(self, model_cls):
        """Return the most recent datetime_modified attribute for the model

        .. note:: This method is intended to be called from
           ``_get_new_edit_data`` but the relevant functionality is not yet
           implemented.
        """
        return None

    def _get_new_edit_data(self, get_params, mode='new'):
        """Return the data to create/edit this resource.

        .. note:: the request GET params (``get_params``) should be used here
        to allow the user to only request fresh data. However, this makes
        assumptions about the Django models that cannot be guaranteed right now
        so this functionality is not currently used.
        """
        result = {}
        for collection, getter in self._get_new_edit_collections(
                mode=mode).items():
            result[collection] = getter()
        return result

    def _get_related_model_getter(self, field):
        related_model_cls = field.model_cls

        def getter(model_cls):
            return [self.inst2rsrc_uri(mi) for mi in model_cls.objects.all()]

        return partial(getter, related_model_cls)

    def _get_enum_getter(self, field):
        def getter(field):
            return [c[0] for c in field.list]
        return partial(getter, field)

    def _django_model_class_to_plural(self, model_cls):
        return self.inflect_p.plural(model_cls.__name__.lower())

    def _get_new_edit_collections(self, mode='new'):
        """Return a dict from collection names (e.g., "users" or "purpose") to
        getter functions that will return all instances of that collection, be
        they Django models or simple strings. This dict is constructed by
        introspecting both ``self.model_cls`` and ``self.schema_cls``.
        """
        collections = {}
        if mode == 'new':
            schema_cls = self.get_create_schema_cls()
        else:
            schema_cls = self.get_update_schema_cls()
        for field_name, field in schema_cls.fields.items():
            if isinstance(field, ResourceURI):
                key = self._django_model_class_to_plural(field.model_cls)
                collections[key] = self._get_related_model_getter(field)
            elif isinstance(field, ForEach):
                first_validator = field.validators[0]
                if isinstance(first_validator, ResourceURI):
                    key = self._django_model_class_to_plural(
                        first_validator.model_cls)
                    collections[key] = self._get_related_model_getter(first_validator)
        return collections


class SchemaState(object):

    def __init__(self, full_dict=None, logged_in_user=None, **kwargs):
        self.full_dict = full_dict
        self.user = logged_in_user
        for key, val in kwargs.items():
            setattr(self, key, val)


def get_eagerloader(model_cls):
    return lambda query_set: query_set


def _get_start_and_end_from_paginator(paginator):
    start = (paginator['page'] - 1) * paginator['items_per_page']
    return (start, start + paginator['items_per_page'])
