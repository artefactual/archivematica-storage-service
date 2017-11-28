#!/bin/bash

set -o errexit
set -o pipefail

function count_migrations() {
    ls storage_service/locations/migrations/*.py | wc -l
}

MIGRATIONS_COUNT_BEFORE=$(count_migrations)
storage_service/manage.py makemigrations
MIGRATIONS_COUNT_AFTER=$(count_migrations)

if [ $MIGRATIONS_COUNT_BEFORE -ne $MIGRATIONS_COUNT_AFTER ]; then
    echo "Migrations are needed"
    exit 1
fi
