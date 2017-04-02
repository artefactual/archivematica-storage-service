FROM python:2.7

ENV DEBIAN_FRONTEND noninteractive
ENV DJANGO_SETTINGS_MODULE storage_service.settings.production
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /src/storage_service
ENV SS_GUNICORN_BIND 0.0.0.0:8000
ENV SS_GUNICORN_CHDIR /src/storage_service
ENV SS_GUNICORN_ACCESSLOG -
ENV SS_GUNICORN_ERRORLOG -
ENV FORWARDED_ALLOW_IPS *

# OS dependencies
RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		gettext \
		p7zip-full \
		rsync \
		unar \
	&& rm -rf /var/lib/apt/lists/*

ADD requirements/ /src/requirements/
RUN pip install -r /src/requirements/production.txt -r /src/requirements/test.txt
ADD ./ /src/
ADD ./install/storage-service.gunicorn-config.py /etc/archivematica/storage-service.gunicorn-config.py

RUN set -ex \
	&& groupadd --gid 333 --system archivematica \
	&& useradd --uid 333 --gid 333 --system archivematica

RUN set -ex \
	&& internalDirs=' \
		/db \
		/src/storage_service/assets \
		/var/archivematica/storage_service \
	' \
	&& mkdir -p $internalDirs \
	&& chown -R archivematica:archivematica $internalDirs

USER archivematica

RUN env \
	DJANGO_SETTINGS_MODULE=storage_service.settings.local \
	SS_DB_URL=mysql://ne:ver@min/d \
		/src/storage_service/manage.py collectstatic --noinput --clear

EXPOSE 8000
WORKDIR /src/storage_service
ENTRYPOINT /usr/local/bin/gunicorn --config=/etc/archivematica/storage-service.gunicorn-config.py storage_service.wsgi:application
