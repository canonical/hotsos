#!/usr/bin/env bash
#
# This file is managed centrally by release-tools and should not be modified
# within individual charm repos.  See the 'global' dir contents for available
# choices of tox.ini for OpenStack Charms:
#     https://github.com/openstack-charmers/release-tools
#
# setuptools 58.0 dropped the support for use_2to3=true which is needed to
# install blessings (an indirect dependency of charm-tools).
#
# More details on the beahvior of tox and virtualenv creation can be found at
# https://github.com/tox-dev/tox/issues/448
#
# This script is wrapper to force the use of the pinned versions early in the
# process when the virtualenv was created and upgraded before installing the
# depedencies declared in the target.
pip install 'pip<20.3' 'setuptools<50.0.0'
pip "$@"
