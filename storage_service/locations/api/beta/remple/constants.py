from django.db.models.fields.related import OneToOneField
from django.db.models.fields import (
    AutoField,
    BigIntegerField,
    BooleanField,
    CharField,
    DateTimeField,
    EmailField,
    IntegerField,
    NullBooleanField,
    PositiveIntegerField,
    TextField,
    UUIDField,
    URLField,
)
from django_extensions.db.fields import UUIDField as UUIDFieldExt
from jsonfield.fields import JSONField
from formencode.validators import (
    Bool,
    Email,
    Int,
    IPAddress,
    OneOf,
    Regex,
    UnicodeString,
    URL,
)

JSONDecodeErrorResponse = {
    'error': 'JSON decode error: the parameters provided were not valid'
             ' JSON.'
}

UNAUTHORIZED_MSG = {
    'error': 'You are not authorized to access this resource.'
}

READONLY_RSLT = {'error': 'This resource is read-only.'}

OK_STATUS = 200
CREATED_STATUS = 201
BAD_REQUEST_STATUS = 400
FORBIDDEN_STATUS = 403
NOT_FOUND_STATUS = 404
METHOD_NOT_ALLOWED_STATUS = 405


django_field2openapi_type = {
    AutoField: 'integer',
    BigIntegerField: 'integer',
    IntegerField: 'integer',
    PositiveIntegerField: 'integer',
    BooleanField: 'boolean',
    NullBooleanField: 'boolean',
    CharField: 'string',
    EmailField: 'string',
    TextField: 'string',
    UUIDField: 'string',
    DateTimeField: 'string',
    JSONField: 'object',
    OneToOneField: 'string',
    UUIDFieldExt: 'string',
    URLField: 'string',
}

django_field2openapi_format = {
    UUIDField: 'uuid',
    DateTimeField: 'date-time',
    URLField: 'uri',
}

python_type2openapi_type = {
    str: 'string',
    int: 'integer',
    float: 'integer',
}

formencode_field2openapi_type = {
    UnicodeString: 'string',
    Regex: 'string',
    Email: 'string',
    OneOf: 'string',  # note: not universally accurate
    IPAddress: 'string',
    URL: 'string',
    Int: 'integer',
    Bool: 'boolean',
}

formencode_field2openapi_format = {
    IPAddress: 'ipv4',
    URL: 'uri',
}
