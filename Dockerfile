ARG TARGET=archivematica-storage-service
ARG UBUNTU_VERSION=22.04

FROM ubuntu:20.04 AS install_osdeps_20.04
RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		mime-support \
    && rm -rf /var/lib/apt/lists/*

FROM ubuntu:22.04 AS install_osdeps_22.04
RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		media-types \
    && rm -rf /var/lib/apt/lists/*

FROM install_osdeps_${UBUNTU_VERSION} AS base

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG PYTHON_VERSION=3.9

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

# OS dependencies
RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		curl \
		gcc \
		gettext \
		git \
		gnupg1 \
		libbz2-dev \
		libffi-dev \
		libldap2-dev \
		liblzma-dev \
		libmysqlclient-dev \
		libncursesw5-dev \
		libreadline-dev \
		libsasl2-dev \
		libsqlite3-dev \
		libssl-dev \
		libxml2-dev \
		libxmlsec1-dev \
		libxslt1-dev \
		libz-dev \
		locales \
		locales-all \
		openssh-client \
		p7zip-full \
		rng-tools \
		rsync \
		unar \
		unzip \
		xz-utils tk-dev \
		zlib1g-dev \
		rclone \
	&& rm -rf /var/lib/apt/lists/*

# Set the locale
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN set -ex \
	&& groupadd --gid ${GROUP_ID} --system archivematica \
	&& useradd --uid ${USER_ID} --gid ${GROUP_ID} --home-dir /var/archivematica --system archivematica

ENV PYENV_ROOT="/pyenv/data"
ENV PATH=$PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

RUN set -ex \
	&& internalDirs=' \
		/pyenv \
		/home/archivematica \
		/src/storage_service/assets \
		/src/storage_service/locations/fixtures \
		/var/archivematica/storage_service \
		/var/archivematica/sharedDirectory \
	' \
	&& mkdir -p $internalDirs \
	&& chown -R archivematica:archivematica $internalDirs

USER archivematica

RUN set -ex \
	&& curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash \
	&& pyenv install ${PYTHON_VERSION} \
	&& pyenv global ${PYTHON_VERSION}

COPY requirements-dev.txt /src/requirements-dev.txt
COPY ./install/storage-service.gunicorn-config.py /etc/archivematica/storage-service.gunicorn-config.py
RUN set -ex \
	&& pyenv exec python${PYTHON_VERSION} -m pip install --upgrade pip setuptools \
	&& pyenv exec python${PYTHON_VERSION} -m pip install --requirement /src/requirements-dev.txt \
	&& pyenv rehash

COPY --chown=${USER_ID}:${GROUP_ID} ./ /src/

# -----------------------------------------------------------------------------

FROM base AS archivematica-storage-service

ARG PYTHON_VERSION=3.9

WORKDIR /src/storage_service

ENV DJANGO_SETTINGS_MODULE storage_service.settings.local
ENV PYTHONPATH /src/storage_service
ENV SS_GUNICORN_BIND 0.0.0.0:8000
ENV SS_GUNICORN_CHDIR /src/storage_service
ENV SS_GUNICORN_ACCESSLOG -
ENV SS_GUNICORN_ERRORLOG -
ENV FORWARDED_ALLOW_IPS *

RUN set -ex \
	&& export SS_DB_URL=mysql://ne:ver@min/d \
	&& pyenv exec python${PYTHON_VERSION} ./manage.py collectstatic --noinput --clear \
	&& pyenv exec python${PYTHON_VERSION} ./manage.py compilemessages

ENV DJANGO_SETTINGS_MODULE storage_service.settings.production

EXPOSE 8000

ENTRYPOINT pyenv exec python${PYTHON_VERSION} -m gunicorn --config=/etc/archivematica/storage-service.gunicorn-config.py storage_service.wsgi:application