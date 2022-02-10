#!/usr/bin/make
PYTHON := /usr/bin/env python3

lint:
	@tox -e pep8

test:
	@echo Starting unit tests...
	@tox -e py27

functional_test:
	@echo Starting Zaza functional tests...
	@tox -e func

bin/charm_helpers_sync.py:
	@mkdir -p bin
	@curl -o bin/charm_helpers_sync.py https://raw.githubusercontent.com/juju/charm-helpers/master/tools/charm_helpers_sync/charm_helpers_sync.py


bin/git_sync.py:
	@mkdir -p bin
	@wget -O bin/git_sync.py https://raw.githubusercontent.com/CanonicalLtd/git-sync/master/git_sync.py

ch-sync: bin/charm_helpers_sync.py
	$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers-hooks.yaml

ceph-sync:  bin/git_sync.py
	$(PYTHON) bin/git_sync.py -d lib -s https://github.com/openstack/charms.ceph.git

sync: ch-sync

publish: lint
	bzr push lp:charms/ceph-osd
	bzr push lp:charms/trusty/ceph-osd
