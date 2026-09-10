#!/usr/bin/env bash
#
# Build the test image and run the integration test suite in Docker Compose.
#
# Environment:
#   INTEGRATION_SERVICE   Compose service that runs pytest. The default
#                         service runs the unit tests and the storage suites;
#                         the authentication suites run in dedicated services
#                         (archivematica-storage-service-oidc, ...) because
#                         their Django settings cannot all be enabled at once.
#   SKIP_DOCKER_BUILD     When set, use the images already built.
#   PYTEST_ADDOPTS        Extra pytest options, e.g. "-k expr".
#   REUSE_TEST_ENV        When set, leave the stack running after the tests.
#
# The exit status is the pytest exit status (or the build's, if it fails).

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "${__dir}"

INTEGRATION_SERVICE="${INTEGRATION_SERVICE:-archivematica-storage-service}"

if [ -z "${SKIP_DOCKER_BUILD}" ]; then
    case "${INTEGRATION_SERVICE}" in
        archivematica-storage-service-oidc)
            # The authentication services reuse the image built by the
            # default service.
            docker compose build archivematica-storage-service
            ;;
        *)
            docker compose build "${INTEGRATION_SERVICE}"
            ;;
    esac

    status=$?

    if [ $status -ne 0 ]; then
        exit $status
    fi
fi

docker compose run --rm "${INTEGRATION_SERVICE}"

status=$?

if [ -z "${REUSE_TEST_ENV}" ]; then
    docker compose down --volumes
fi

exit $status
