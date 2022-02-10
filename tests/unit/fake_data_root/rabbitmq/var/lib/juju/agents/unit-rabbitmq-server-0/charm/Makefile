#!/usr/bin/make
PYTHON := /usr/bin/env python3
CHARM_DIR := $(PWD)
HOOKS_DIR := $(PWD)/hooks
TEST_PREFIX := PYTHONPATH=$(HOOKS_DIR)

clean:
	rm -f .coverage .testrepository
	find . -name '*.pyc' -delete

lint:
	@tox -e pep8

bin/charm_helpers_sync.py:
	@mkdir -p bin
	@curl -o bin/charm_helpers_sync.py https://raw.githubusercontent.com/juju/charm-helpers/master/tools/charm_helpers_sync/charm_helpers_sync.py


sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers-hooks.yaml

test:
	@echo Starting unit tests...
	@tox -e py36

functional_test:
	@echo Starting Zaza tests...
	@tox -e func
