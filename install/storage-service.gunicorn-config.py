# Documentation: http://docs.gunicorn.org/en/stable/configure.html
# Example: https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py

import os

# http://docs.gunicorn.org/en/stable/settings.html#user
user = os.environ.get('SS_GUNICORN_USER', 'archivematica')

# http://docs.gunicorn.org/en/stable/settings.html#group
group = os.environ.get('SS_GUNICORN_GROUP', 'archivematica')

# http://docs.gunicorn.org/en/stable/settings.html#bind
bind = os.environ.get('SS_GUNICORN_BIND', '127.0.0.1:8001')

# http://docs.gunicorn.org/en/stable/settings.html#workers
workers = os.environ.get('SS_GUNICORN_WORKERS', '1')

# http://docs.gunicorn.org/en/stable/settings.html#worker-class
# WARNING: if ``worker_class`` is set to ``'gevent'``, then
# ``BAG_VALIDATION_NO_PROCESSES`` in settings/base.py *must* be set to 1.
# Otherwise reingest will fail at bagit validate. See
# https://github.com/artefactual/archivematica/issues/708
worker_class = os.environ.get('SS_GUNICORN_WORKER_CLASS', 'gevent')

# http://docs.gunicorn.org/en/stable/settings.html#timeout
timeout = os.environ.get('SS_GUNICORN_TIMEOUT', '172800')

# http://docs.gunicorn.org/en/stable/settings.html#reload
reload = os.environ.get('SS_GUNICORN_RELOAD', 'false')

# http://docs.gunicorn.org/en/stable/settings.html#reload-engine
reload_engine = os.environ.get('SS_GUNICORN_RELOAD_ENGINE', 'auto')

# http://docs.gunicorn.org/en/stable/settings.html#chdir
chdir = os.environ.get('SS_GUNICORN_CHDIR', '/usr/lib/archivematica/storage-service')

# http://docs.gunicorn.org/en/stable/settings.html#accesslog
accesslog = os.environ.get('SS_GUNICORN_ACCESSLOG', None)

# http://docs.gunicorn.org/en/stable/settings.html#errorlog
errorlog = os.environ.get('SS_GUNICORN_ERRORLOG', '-')

# http://docs.gunicorn.org/en/stable/settings.html#loglevel
loglevel = os.environ.get('SS_GUNICORN_LOGLEVEL', 'info')

# http://docs.gunicorn.org/en/stable/settings.html#proc-name
proc_name = os.environ.get('SS_GUNICORN_PROC_NAME', 'archivematica-storage-service')

# http://docs.gunicorn.org/en/stable/settings.html#sendfile
sendfile = os.environ.get('SS_GUNICORN_SENDFILE', 'false')
