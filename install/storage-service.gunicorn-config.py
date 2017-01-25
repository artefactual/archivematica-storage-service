# Documentation: http://docs.gunicorn.org/en/stable/configure.html
# Example: https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py

# http://docs.gunicorn.org/en/stable/settings.html#user
user = "archivematica"

# http://docs.gunicorn.org/en/stable/settings.html#group
group = "archivematica"

# http://docs.gunicorn.org/en/stable/settings.html#bind
bind = "127.0.0.1:8001"

# http://docs.gunicorn.org/en/stable/settings.html#workers
workers = "4"

# http://docs.gunicorn.org/en/stable/settings.html#timeout
timeout = "172800"

# http://docs.gunicorn.org/en/stable/settings.html#reload
reload = False

# http://docs.gunicorn.org/en/stable/settings.html#chdir
chdir = "/usr/lib/archivematica/storage-service"

# http://docs.gunicorn.org/en/stable/settings.html#raw-env
raw_env = [
    "EMAIL_HOST_PASSWORD=",
    "SS_DB_NAME=/var/archivematica/storage-service/storage.db",
    "DJANGO_STATIC_ROOT=/usr/lib/archivematica/storage-service/assets",
    "SS_DB_PASSWORD=",
    "SS_DB_USER=",
    "SS_DB_HOST=",
    "DJANGO_SETTINGS_MODULE=storage_service.settings.production",
    "EMAIL_PORT=25",
    "DJANGO_SECRET_KEY=<replace-with-key>",
    "EMAIL_HOST_USER=",
    "EMAIL_HOST=localhost",
]

# http://docs.gunicorn.org/en/stable/settings.html#accesslog
accesslog = "/var/log/archivematica/storage-service/gunicorn.access_log"

# http://docs.gunicorn.org/en/stable/settings.html#errorlog
errorlog = "/var/log/archivematica/storage-service/gunicorn.error_log"

# http://docs.gunicorn.org/en/stable/settings.html#loglevel
loglevel = "info"

# http://docs.gunicorn.org/en/stable/settings.html#proc-name
proc_name = "archivematica-storage-service"

# http://docs.gunicorn.org/en/stable/settings.html#pythonpath
pythonpath = ""

# http://docs.gunicorn.org/en/stable/settings.html#sendfile
sendfile = True
