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
import sys
import textwrap

import requests


logger = logging.getLogger(__name__)
log_lvl = logging.INFO
out_hdlr = logging.StreamHandler(sys.stdout)
logger.addHandler(out_hdlr)
logger.setLevel(log_lvl)


OPENAPI_SPEC = None


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
    except requests.exceptions.ConnectionError as err:
        msg = 'Connection error {}'.format(err)
        logger.error(msg)
        raise HTTPError(msg[:30])
    except Exception as err:
        msg = 'Unknown error making HTTP request {}'.format(err)
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
        msg = (
            'Unknown status code {status_code} ("{reason}") returned for'
            '{method} request to {url}'.format(
                status_code=status_code, reason=response.reason, method=method,
                url=url))
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
        if (not arg_format) and arg_type == 'list':
            arg_format = arg_cfg.get('items', {}).get('format')
            if arg_format:
                arg_format = 'each element is a {}'.format(arg_format)
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


def decapitalize(string):
    return string[:1].lower() + string[1:] if string else ''


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
    kwarg_names = []
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
        {
            '__init__': __init__,
            'get_auth_headers': get_auth_headers,
            'openapi_spec': openapi_spec,
            '_call_url_json': _call_url_json,
            '_handle_response': _handle_response,
            '_serialize_params': _serialize_params,
        }
    )


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
