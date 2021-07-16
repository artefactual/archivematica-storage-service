ARG TARGET=archivematica-storage-service
ARG PYTHON_VERSION=3.6

FROM ubuntu:18.04 AS base

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

# OS dependencies
RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		curl \
		gettext \
		git \
		gnupg1 \
		libldap2-dev \
		libmysqlclient-dev \
		libpq-dev \
		libsasl2-dev \
		locales \
		locales-all \
		p7zip-full \
		rsync \
		software-properties-common \
		unar \
	&& rm -rf /var/lib/apt/lists/*

# Set the locale
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN set -ex \
	&& groupadd --gid 333 --system archivematica \
	&& useradd --uid 333 --gid 333 --system archivematica

RUN set -ex \
	&& internalDirs=' \
		/db \
		/src/storage_service/assets \
		/src/storage_service/locations/fixtures \
		/var/archivematica/storage_service \
		/var/archivematica/sharedDirectory \
	' \
	&& mkdir -p $internalDirs \
	&& chown -R archivematica:archivematica $internalDirs

COPY requirements/ /src/requirements/
COPY ./install/storage-service.gunicorn-config.py /etc/archivematica/storage-service.gunicorn-config.py

# -----------------------------------------------------------------------------

FROM base AS python3

ARG PYTHON_VERSION=3.6

RUN set -ex \
	&& add-apt-repository --no-update --yes ppa:deadsnakes/ppa \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		python${PYTHON_VERSION}-dev python${PYTHON_VERSION}-distutils\
	&& rm -rf /var/lib/apt/lists/*

RUN set -ex \
	&& curl -s https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VERSION} \
	&& update-alternatives --install /usr/bin/python python /usr/bin/python${PYTHON_VERSION} 10

RUN pip${PYTHON_VERSION} install -q -r /src/requirements/production.txt -r /src/requirements/test.txt

COPY . /src

# -----------------------------------------------------------------------------

FROM python3 AS archivematica-storage-service

WORKDIR /src/storage_service

USER archivematica

ENV DJANGO_SETTINGS_MODULE storage_service.settings.local
ENV PYTHONPATH /src/storage_service
ENV SS_GUNICORN_BIND 0.0.0.0:8000
ENV SS_GUNICORN_CHDIR /src/storage_service
ENV SS_GUNICORN_ACCESSLOG -
ENV SS_GUNICORN_ERRORLOG -
ENV FORWARDED_ALLOW_IPS *

RUN set -ex \
	&& export SS_DB_URL=mysql://ne:ver@min/d \
	&& ./manage.py collectstatic --noinput --clear \
	&& ./manage.py compilemessages

ENV DJANGO_SETTINGS_MODULE storage_service.settings.production

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/gunicorn", "--config=/etc/archivematica/storage-service.gunicorn-config.py", "storage_service.wsgi:application"]
