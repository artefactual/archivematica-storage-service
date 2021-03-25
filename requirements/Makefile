.PHONY: pip-compile
pip-compile:  # Compile pip requirements
	pip-compile --allow-unsafe --output-file base.txt base.in
	pip-compile --allow-unsafe --output-file local.txt local.in
	pip-compile --allow-unsafe --output-file production.txt production.in
	pip-compile --allow-unsafe --output-file test.txt test.in

.PHONY: pip-compile-py3
pip-compile-py3:  # Compile pip requirements (Python 3)
	pip-compile --allow-unsafe --output-file base-py3.txt base.in
	pip-compile --allow-unsafe --output-file local-py3.txt local-py3.in
	pip-compile --allow-unsafe --output-file production-py3.txt production-py3.in
	pip-compile --allow-unsafe --output-file test-py3.txt test-py3.in

.PHONY: pip-upgrade
pip-upgrade:  # Upgrade pip requirements
	pip-compile --allow-unsafe --upgrade --output-file base.txt base.in
	pip-compile --allow-unsafe --upgrade --output-file local.txt local.in
	pip-compile --allow-unsafe --upgrade --output-file production.txt production.in
	pip-compile --allow-unsafe --upgrade --output-file test.txt test.in
