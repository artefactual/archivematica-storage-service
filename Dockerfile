ARG TARGET=archivematica-storage-service
ARG UBUNTU_VERSION=24.04
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG NODE_VERSION=24
ARG UV_VERSION=0.11.30
ARG UV_DIGEST=sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47
ARG PYTHON_INSTALL_DIR=/python

# Pin the Docker tool image independently for reproducible builds.
FROM ghcr.io/astral-sh/uv:${UV_VERSION}@${UV_DIGEST} AS uv

# -----------------------------------------------------------------------------

FROM ubuntu:${UBUNTU_VERSION} AS base-builder

ARG PYTHON_INSTALL_DIR=/python

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		ca-certificates \
		curl \
		git \
		libldap2-dev \
		libmysqlclient-dev \
		libsasl2-dev \
		libsqlite3-dev \
		locales \
		pkg-config \
	&& rm -rf /var/lib/apt/lists/* /var/cache/apt/*

RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

ENV PATH=${PYTHON_INSTALL_DIR}/venv/bin:$PATH

# -----------------------------------------------------------------------------

FROM base-builder AS python-builder

ARG PYTHON_VERSION
ARG PYTHON_INSTALL_DIR=/python

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_CACHE_DIR=/root/.cache/uv/python
ENV UV_PYTHON_INSTALL_DIR=${PYTHON_INSTALL_DIR}/managed
ENV UV_PYTHON_PREFERENCE=only-managed
ENV UV_PROJECT_ENVIRONMENT=${PYTHON_INSTALL_DIR}/venv

COPY --from=uv --link /uv /usr/local/bin/uv

WORKDIR /src

COPY --link .python-version pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
	set -ex \
	&& if [ -n "${PYTHON_VERSION}" ]; then \
		uv python install --no-bin "${PYTHON_VERSION}"; \
		uv sync --locked --no-install-project --python "${PYTHON_VERSION}"; \
	else \
		uv python install --no-bin; \
		uv sync --locked --no-install-project; \
	fi

# -----------------------------------------------------------------------------

FROM node:${NODE_VERSION} AS archivematica-storage-service-frontend-builder

ARG USER_ID
ARG GROUP_ID

WORKDIR /src/src/archivematica/storage_service/frontend

COPY --link src/archivematica/storage_service/frontend/package.json /src/src/archivematica/storage_service/frontend/package.json
COPY --link src/archivematica/storage_service/frontend/package-lock.json /src/src/archivematica/storage_service/frontend/package-lock.json

RUN --mount=type=cache,target=/root/.npm,sharing=locked \
	set -ex \
	&& npm pkg delete scripts.prepare \
	&& npm clean-install

COPY --link src/archivematica/storage_service/frontend /src/src/archivematica/storage_service/frontend

RUN npm run build \
	&& chown -R ${USER_ID}:${GROUP_ID} /src/src/archivematica/storage_service/frontend/node_modules

# -----------------------------------------------------------------------------

FROM base-builder AS base

ARG USER_ID
ARG GROUP_ID
ARG PYTHON_INSTALL_DIR=/python

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		gcc \
		gettext \
		gnupg2 \
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

# Ensure the requested UID/GID do not clash with defaults in the Ubuntu base
# image. We look up any existing user/group that already uses such identifiers
# and remove them to avoid conflicts before creating the archivematica account.
RUN set -ex \
	&& { \
		grp=$(getent group "${GROUP_ID}" | cut -d: -f1 || true); \
		if [ -n "${grp}" ]; then groupdel --force "${grp}"; fi; \
		usr=$(getent passwd "${USER_ID}" | cut -d: -f1 || true); \
		if [ -n "${usr}" ]; then userdel --remove "${usr}"; fi; \
	} \
	&& groupadd --gid ${GROUP_ID} --system archivematica \
	&& useradd --uid ${USER_ID} --gid ${GROUP_ID} --home-dir /var/archivematica --system archivematica

RUN set -ex \
	&& internalDirs=' \
		/home/archivematica \
		/src/archivematica/storage_service/assets \
		/src/archivematica/storage_service/locations/fixtures \
		/var/archivematica/storage_service \
		/var/archivematica/sharedDirectory \
	' \
	&& mkdir -p $internalDirs \
	&& chown -R archivematica:archivematica $internalDirs

USER archivematica

COPY --chown=${USER_ID}:${GROUP_ID} --from=python-builder --link ${PYTHON_INSTALL_DIR} ${PYTHON_INSTALL_DIR}
COPY --from=uv --link /uv /usr/local/bin/uv
COPY --chown=${USER_ID}:${GROUP_ID} --link ./install/storage-service.gunicorn-config.py /etc/archivematica/storage-service.gunicorn-config.py

ENV PYTHONPATH=/src/src

# -----------------------------------------------------------------------------

FROM base AS archivematica-storage-service

ARG USER_ID
ARG GROUP_ID

ENV DJANGO_SETTINGS_MODULE=archivematica.storage_service.storage_service.settings.local
ENV SS_GUNICORN_BIND=0.0.0.0:8000
ENV SS_GUNICORN_ACCESSLOG=-
ENV SS_GUNICORN_ERRORLOG=-
ENV FORWARDED_ALLOW_IPS=*

COPY --chown=${USER_ID}:${GROUP_ID} --link . /src/
COPY --chown=${USER_ID}:${GROUP_ID} --from=archivematica-storage-service-frontend-builder --link /src/src/archivematica/storage_service/frontend/dist /src/src/archivematica/storage_service/frontend/dist

RUN set -ex \
	&& export SS_DB_URL=mysql://ne:ver@min/d \
	&& python -m archivematica.storage_service.manage collectstatic --noinput --clear \
	&& python -m archivematica.storage_service.manage compilemessages

ENV DJANGO_SETTINGS_MODULE=archivematica.storage_service.storage_service.settings.production

EXPOSE 8000

ENTRYPOINT ["python", "-m", "gunicorn", "--config=/etc/archivematica/storage-service.gunicorn-config.py", "archivematica.storage_service.storage_service.wsgi:application"]

# -----------------------------------------------------------------------------

FROM base AS archivematica-storage-service-tests

ARG USER_ID
ARG GROUP_ID

USER root

RUN set -ex \
	&& python -m playwright install-deps firefox \
	&& mkdir -p /var/archivematica/.cache/ms-playwright \
	&& chown -R archivematica:archivematica /var/archivematica/

USER archivematica

RUN set -ex \
	&& python -m playwright install firefox

COPY --chown=${USER_ID}:${GROUP_ID} --link . /src/

# Copy frontend assets out of where /src is bind-mounted during tests.
COPY --chown=${USER_ID}:${GROUP_ID} --from=archivematica-storage-service-frontend-builder --link /src/src/archivematica/storage_service/frontend/dist /opt/ss-frontend-dist

# -----------------------------------------------------------------------------

FROM ${TARGET}
