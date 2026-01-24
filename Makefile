SHELL:=/bin/bash
PYTHON ?= python3
.DEFAULT_GOAL=_help

.PHONY: _help
_help:
	@printf "\nUsage: make <command>, valid commands:\n\n"
	@grep -h "##H@@" $(MAKEFILE_LIST) | grep -v IGNORE_ME | sed -e 's/##H@@//' | column -t -s $$'\t'

# help: ## Show this help
# 	@grep -Eh '\s##\s' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'


REMOTE_HEAD ?= origin/master
PY_CHANGED_FILES ?= $(shell git diff --name-only --diff-filter=MACU $(REMOTE_HEAD) '*.py')
PY_CHANGED_FILES_FLAG ?= $(if $(PY_CHANGED_FILES),1,)
SH_ALL_FILES ?= $(shell git ls-files '*.sh')
PRETTIER_ALL_FILES ?= $(shell git ls-files '*.js' '*.css' '*.html' '*.md' '*.yaml' '*.yml')

.PHONY: format
format:	##H@@ Format with black & isort
	# ==================================================
	# formatting
	# ==================================================
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# prettier     (optional)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	-prettier --write ${PRETTIER_ALL_FILES}
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# shfmt        (optional)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	-shfmt -w ${SH_ALL_FILES}
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# isort
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		isort ${PY_CHANGED_FILES}; \
	fi
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# black
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		black ${PY_CHANGED_FILES}; \
	fi
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# ruff (format)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		ruff check --fix --exit-zero $(ARGS) ${PY_CHANGED_FILES}; \
	fi

.PHONY: lint
lint: ruff pylint mypy
lint:	##H@@ Lint with ruff, pylint, and mypy


.PHONY: ruff
ruff:
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# ruff (lint)
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		ruff check ${PY_CHANGED_FILES}; \
	fi

.PHONY: pylint
pylint:
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# pylint
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		pylint -j 0 ${PY_CHANGED_FILES}; \
	fi

.PHONY: mypy
mypy:
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	# mypy
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	-if [ -n "${PY_CHANGED_FILES_FLAG}" ]; then \
		mypy ${PY_CHANGED_FILES}; \
	fi


# -include .env

# Installation
.PHONY: deps
deps:	##H@@ Install dependencies
	$(PYTHON) -m pip install --no-user ".[dev]"


.PHONY: test/unit
test/unit:	##H@@ Run Unit tests only
	$(PYTHON) -m coverage run -p -m pytest getmyancestors/tests


# Generate targets for all test files (enables autocomplete)
TEST_FILES := $(wildcard getmyancestors/tests/test_*.py)
TEST_TARGETS := $(patsubst getmyancestors/tests/%.py,test/unit/%,$(TEST_FILES))

.PHONY: $(TEST_TARGETS)
$(TEST_TARGETS): test/unit/%:
	pytest getmyancestors/tests/$*.py -v


.PHONY: test
test:	##H@@ Run unit & E2E tests
test: test/unit test/offline test/install test/cov

.PHONY: test/
test/: test

.PHONY: test/cov
test/cov:	##H@@ Combine all coverage data and show report
	-$(PYTHON) -m coverage combine
	$(PYTHON) -m coverage report


.PHONY: test/install
test/install:	##H@@ Run installation tests
	$(PYTHON) -m coverage run -p -m pytest tests/test_installation.py


.PHONY: test/offline
test/offline:	##H@@ Run offline verification (requires fixtures)
	$(PYTHON) -m pytest tests/offline_test.py


.PHONY: clean
clean:	##H@@ Clean up build files/cache
	rm -rf *.egg-info build dist .coverage .coverage.*
	rm -rf .tmp .pytest_cache .ruff_cache .mypy_cache
	# One unified find command to clean python artifacts while ignoring .venv
	find . -type d -name ".venv" -prune -o \
		\( \( -name "__pycache__" -o -name "http_cache" \) -type d -o \
		\( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" -o -name "*.so" \) -type f \) \
		-exec rm -rf {} +
	@echo "✓ Cleaned build files, caches, and test artifacts"
