# Copyright 2015-2016 Canonical Ltd.
#
# This file is part of the Coordinator Layer for Juju.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from charmhelpers.core import hookenv
from charms.coordinator import coordinator, log
import charms.reactive


def initialize_coordinator_state():
    '''
    The coordinator.granted.{lockname} state will be set and the
    coordinator.requested.{lockname} state removed for every lock
    granted to the currently running hook.

    The coordinator.requested.{lockname} state will remain set for locks
    not yet granted
    '''
    log('Initializing coordinator layer')

    requested = set(coordinator.requests.get(hookenv.local_unit(), {}).keys())
    previously_requested = set(state.split('.', 2)[2]
                               for state in charms.reactive.bus.get_states()
                               if state.startswith('coordinator.requested.'))

    granted = set(coordinator.grants.get(hookenv.local_unit(), {}).keys())
    previously_granted = set(state.split('.', 2)[2]
                             for state in charms.reactive.bus.get_states()
                             if state.startswith('coordinator.granted.'))

    # Set reactive state for requested locks.
    for lock in requested:
        log('Requested {} lock'.format(lock), hookenv.DEBUG)
        charms.reactive.set_state('coordinator.requested.{}'.format(lock))

    # Set reactive state for locks that have been granted.
    for lock in granted:
        log('Granted {} lock'.format(lock), hookenv.DEBUG)
        charms.reactive.set_state('coordinator.granted.{}'.format(lock))

    # Remove reactive state for locks that have been released.
    for lock in (previously_granted - granted):
        log('Dropped {} lock'.format(lock), hookenv.DEBUG)
        charms.reactive.remove_state('coordinator.granted.{}'.format(lock))

    # Remove requested state for locks no longer requested and not granted.
    for lock in (previously_requested - requested - granted):
        log('Request for {} lock was dropped'.format(lock), hookenv.DEBUG)
        charms.reactive.remove_state('coordinator.requested.{}'.format(lock))


# Per https://github.com/juju-solutions/charms.reactive/issues/33,
# this module may be imported multiple times so ensure the
# initialization hook is only registered once. I have to piggy back
# onto the namespace of a module imported before reactive discovery
# to do this.
if not hasattr(charms.reactive, '_coordinator_registered'):
    hookenv.atstart(initialize_coordinator_state)
    charms.reactive._coordinator_registered = True
