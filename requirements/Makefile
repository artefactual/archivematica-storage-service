.PHONY: pip-compile
pip-compile:  # Compile pip requirements
	pip-compile --allow-unsafe --output-file base.txt base.in
	pip-compile --allow-unsafe --output-file local.txt local.in
	pip-compile --allow-unsafe --output-file production.txt production.in
	pip-compile --allow-unsafe --output-file test.txt test.in

.PHONY: pip-upgrade
pip-upgrade:  # Upgrade pip requirements
	pip-compile --allow-unsafe --upgrade --output-file base.txt base.in
	pip-compile --allow-unsafe --upgrade --output-file local.txt local.in
	pip-compile --allow-unsafe --upgrade --output-file production.txt production.in
	pip-compile --allow-unsafe --upgrade --output-file test.txt test.in
