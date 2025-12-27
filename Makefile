LINT_LOCS ?= getmyancestors/

.PHONY: lint
lint:
	flake8 $(LINT_LOCS)
	black $(LINT_LOCS)
	isort $(LINT_LOCS)
	pylint $(LINT_LOCS)
	mypy $(LINT_LOCS)

.PHONY: test
test:
	coverage run -m pytest -svv tests/
	coverage report -m
