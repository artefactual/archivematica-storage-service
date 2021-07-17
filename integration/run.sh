#!/usr/bin/env bash

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd ${__dir}

env COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 BUILDKIT_PROGRESS=plain docker-compose build minio mysql archivematica-storage-service

docker-compose run --rm archivematica-storage-service
__exit=$?

docker-compose down --volumes

exit ${__exit}
