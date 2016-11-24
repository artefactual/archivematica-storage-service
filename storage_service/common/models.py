#!/usr/bin/env python

import logging

from django.contrib.auth import models as auth_models
from django.db.models import signals

logger = logging.getLogger(__name__)

# Create our own test user automatically.

def create_testuser(app, created_models, verbosity, **kwargs):
    try:
        auth_models.User.objects.get(username='test')
    except auth_models.User.DoesNotExist:
        logger.info('Creating test user -- login: test, password: test')
        assert auth_models.User.objects.create_superuser('test', 'x@x.com', 'test')
    else:
        logger.info('Test user already exists.')

signals.post_syncdb.connect(create_testuser,
    sender=auth_models, dispatch_uid='common.models.create_testuser')
