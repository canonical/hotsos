#!/usr/bin/env python3
#
# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys


_path = os.path.dirname(os.path.realpath(__file__))
_hooks = os.path.abspath(os.path.join(_path, '../hooks'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_hooks)


from charmhelpers.contrib.openstack.utils import (
    do_action_openstack_upgrade,
)
from charmhelpers.core.hookenv import (
    relation_ids,
)
from nova_compute_utils import do_openstack_upgrade
from nova_compute_hooks import (
    config_changed,
    CONFIGS,
    neutron_plugin_joined,
    nova_ceilometer_joined,
)


def openstack_upgrade():
    """Upgrade packages to config-set Openstack version.

    If the charm was installed from source we cannot upgrade it.
    For backwards compatibility a config flag must be set for this
    code to run, otherwise a full service level upgrade will fire
    on config-changed."""

    if (do_action_openstack_upgrade('nova-common',
                                    do_openstack_upgrade,
                                    CONFIGS)):
        # we should restart the container scoped (subordinate) plugins after a
        # managed openstack upgrade see: BUG#1835557
        for rid in relation_ids('neutron-plugin'):
            neutron_plugin_joined(rid, remote_restart=True)
        for rid in relation_ids('nova-ceilometer'):
            nova_ceilometer_joined(rid, remote_restart=True)
        # NOTE(ajkavanagh) - if unit is paused (usually true for managed
        # upgrade) then the config_changed() function is a no-op
        config_changed()


if __name__ == '__main__':
    openstack_upgrade()
