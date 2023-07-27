#!/usr/bin/env bash

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd ${__dir}

docker compose build archivematica-storage-service

status=$?

if [ $status -ne 0 ]; then
    exit $status
fi

docker compose run --rm archivematica-storage-service

status=$?

docker compose down --volumes

exit $status
