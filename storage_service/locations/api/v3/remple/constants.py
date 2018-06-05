JSONDecodeErrorResponse = {
    'error': 'JSON decode error: the parameters provided were not valid'
             ' JSON.'
}

UNAUTHORIZED_MSG = {
    'error': 'You are not authorized to access this resource.'
}

READONLY_RSLT = {'error': 'This resource is read-only.'}

OK_STATUS = 200
BAD_REQUEST_STATUS = 400
FORBIDDEN_STATUS = 403
NOT_FOUND_STATUS = 404
METHOD_NOT_ALLOWED_STATUS = 405


django_field_class2openapi_type = {
    'AutoField': 'integer',
    'BigIntegerField': 'integer',
    'IntegerField': 'integer',
    'BooleanField': 'boolean',
    'CharField': 'string',
    'TextField': 'string',
    'UUIDField': 'string',
    'DateTimeField': 'string',
    'JSONField': 'object',
}

django_field_class2openapi_format = {
    'UUIDField': 'uuid',
    'DateTimeField': 'date-time',
}

python_type2openapi_type = {
    str: 'string',
    int: 'integer',
    float: 'integer',
}

formencode_field_class2openapi_type = {
    'UnicodeString': 'string',
    'OneOf': 'string',  # note: not universally accurate
    'IPAddress': 'string',
    'URL': 'string',
    'Int': 'integer',
    'Bool': 'boolean',
}

formencode_field_class2openapi_format = {
    'IPAddress': 'ipv4',
    'URL': 'uri',
}
