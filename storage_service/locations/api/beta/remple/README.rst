================================================================================
  Remple: REST Simple
================================================================================

Usage::

    >>> from remple import API, Resources
    >>> class Users(Resources):
    ...     model_cls = User  # A Django model class
    ...     schema_cls = UserSchema  # A Formencode class
    >>> resources = {'user': {'resource_cls': Users}}
    >>> api = API(api_version='0.1.0', service_name='User City!')
    >>> api.register_resources(resources)
    >>> urls = api.get_urlpatterns()  # Include these in Django urlpatterns
