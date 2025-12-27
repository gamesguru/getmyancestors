SHELL:=/bin/bash
.DEFAULT_GOAL=_help

# NOTE: must put a <TAB> character and two pound "\t##" to show up in this list.  Keep it brief! IGNORE_ME
.PHONY: _help
_help:
	@printf "\nUsage: make <command>, valid commands:\n\n"
	@grep "##" $(MAKEFILE_LIST) | grep -v IGNORE_ME | sed -e 's/##//' | column -t -s $$'\t'


LINT_LOCS ?= getmyancestors/

.PHONY: lint
lint: 	## Lint (not implemented, no-op)
	flake8 $(LINT_LOCS)
#	black $(LINT_LOCS)
#	isort $(LINT_LOCS)
	pylint $(LINT_LOCS)
	mypy $(LINT_LOCS)

.PHONY: test
test:	## Run tests & show coverage
	coverage run
	-coverage report
