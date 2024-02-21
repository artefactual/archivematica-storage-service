ARG TARGET=archivematica-storage-service
ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION} AS base-builder

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG PYTHON_VERSION=3.9
ARG PYENV_DIR=/pyenv

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		ca-certificates \
		curl \
		git \
		libldap2-dev \
		libmysqlclient-dev \
		libsasl2-dev \
		libsqlite3-dev \
		locales \
	&& rm -rf /var/lib/apt/lists/* /var/cache/apt/*

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

ENV PYENV_ROOT=${PYENV_DIR}/data
ENV PATH=$PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH

# -----------------------------------------------------------------------------

FROM base-builder AS pyenv-builder

ARG PYTHON_VERSION=3.9

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		libbz2-dev \
		libffi-dev \
		liblzma-dev \
		libncursesw5-dev \
		libreadline-dev \
		libsqlite3-dev \
		libssl-dev \
		libxml2-dev \
		libxmlsec1-dev \
		tk-dev \
		xz-utils \
		zlib1g-dev \
	&& rm -rf /var/lib/apt/lists/* /var/cache/apt/*

RUN set -ex \
	&& curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash \
	&& pyenv install ${PYTHON_VERSION} \
	&& pyenv global ${PYTHON_VERSION}

COPY --link requirements-dev.txt /src/requirements-dev.txt

RUN set -ex \
	&& pyenv exec python3 -m pip install --upgrade pip setuptools \
	&& pyenv exec python3 -m pip install --requirement /src/requirements-dev.txt \
	&& pyenv rehash

# -----------------------------------------------------------------------------

FROM base-builder as base

ARG USER_ID=1000
ARG GROUP_ID=1000

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		gcc \
		gettext \
		gnupg1 \
		libffi-dev \
		libldap2-dev \
		libmysqlclient-dev \
		libsasl2-dev \
		libssl-dev \
		libxml2-dev \
		libxslt1-dev \
		libz-dev \
		media-types \
		p7zip-full \
		rclone \
		rng-tools-debian \
		rsync \
		unar \
	&& rm -rf /var/lib/apt/lists/*

RUN set -ex \
	&& groupadd --gid ${GROUP_ID} --system archivematica \
	&& useradd --uid ${USER_ID} --gid ${GROUP_ID} --home-dir /var/archivematica --system archivematica

RUN set -ex \
	&& internalDirs=' \
		/home/archivematica \
		/src/storage_service/assets \
		/src/storage_service/locations/fixtures \
		/var/archivematica/storage_service \
		/var/archivematica/sharedDirectory \
	' \
	&& mkdir -p $internalDirs \
	&& chown -R archivematica:archivematica $internalDirs

USER archivematica

COPY --chown=${USER_ID}:${GROUP_ID} --from=pyenv-builder --link /pyenv /pyenv
COPY --link ./install/storage-service.gunicorn-config.py /etc/archivematica/storage-service.gunicorn-config.py
COPY --chown=${USER_ID}:${GROUP_ID} --link . /src/

# -----------------------------------------------------------------------------

FROM base AS archivematica-storage-service

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
	&& pyenv exec python3 ./manage.py collectstatic --noinput --clear \
	&& pyenv exec python3 ./manage.py compilemessages

ENV DJANGO_SETTINGS_MODULE storage_service.settings.production

EXPOSE 8000

ENTRYPOINT ["pyenv", "exec", "python3", "-m", "gunicorn", "--config=/etc/archivematica/storage-service.gunicorn-config.py", "storage_service.wsgi:application"]
