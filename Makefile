UV ?= uv
DOCKER ?= docker
DOCKER_IMAGE ?= archivematica-storage-service:latest
PYTHON_VERSION ?= $(shell tr -d '\n' < $(CURDIR)/.python-version)
PYTEST_ARGS ?=

.PHONY: lock
lock:  # Update the lockfile without upgrading locked dependencies
	$(UV) lock

.PHONY: lock-check
lock-check:  # Verify that the lockfile is up to date
	$(UV) lock --check

.PHONY: upgrade
upgrade:  # Upgrade all locked dependencies
	$(UV) lock --upgrade

.PHONY: sync
sync:  # Sync the project and development dependencies
	$(UV) sync --locked

.PHONY: sync-runtime
sync-runtime:  # Sync only the project and runtime dependencies
	$(UV) sync --locked --no-dev

.PHONY: lint
lint:  # Run all pre-commit checks
	$(UV) run --locked pre-commit run --all-files --show-diff-on-failure

.PHONY: migrations
migrations:  # Check for missing Django migrations
	DJANGO_SETTINGS_MODULE=archivematica.storage_service.storage_service.settings.test \
		DJANGO_SECRET_KEY=1234 BOTO_CONFIG=/dev/null \
		$(UV) run --locked django-admin makemigrations --check --dry-run

.PHONY: check
check: lock-check lint migrations  # Verify the lockfile and run all checks

.PHONY: test
test:  # Run the test suite; pass options with PYTEST_ARGS
	DJANGO_SECRET_KEY=1234 BOTO_CONFIG=/dev/null \
		$(UV) run --locked pytest $(PYTEST_ARGS)

.PHONY: docker-build
docker-build:  # Build the Storage Service image
	$(DOCKER) build \
		--target archivematica-storage-service \
		--build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
		--tag $(DOCKER_IMAGE) \
		.
