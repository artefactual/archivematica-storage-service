#!/usr/bin/env bash

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd ${__dir}

env COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker-compose build archivematica-storage-service

docker-compose run --rm archivematica-storage-service

status=$?

docker-compose down --volumes

exit $status
