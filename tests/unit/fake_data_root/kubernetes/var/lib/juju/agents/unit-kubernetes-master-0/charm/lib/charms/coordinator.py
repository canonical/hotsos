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

import importlib

from charmhelpers.coordinator import BaseCoordinator
from charmhelpers.core import hookenv
from charms import reactive
import charms.layer


__all__ = ['coordinator', 'acquire']


def acquire(lock):
    """
    Sets either the coordinator.granted.{lockname} or
    coordinator.requested.{lockname} state.

    Returns True if the lock could be immediately granted.

    If locks cannot be granted immediately, they will be granted
    in a future hook and the coordinator.granted.{lockname} state set.
    """
    global coordinator
    if coordinator.acquire(lock):
        s = 'coordinator.granted.{}'.format(lock)
        if not reactive.is_state(s):
            log('Granted {} lock'.format(lock), hookenv.DEBUG)
            reactive.set_state('coordinator.granted.{}'.format(lock))
        return True
    else:
        log('Requested {} lock'.format(lock), hookenv.DEBUG)
        reactive.set_state('coordinator.requested.{}'.format(lock))
        return False


options = charms.layer.options('coordinator')


def log(msg, level=hookenv.INFO):
    lmap = {hookenv.DEBUG: 1,
            hookenv.INFO: 2,
            hookenv.WARNING: 3,
            hookenv.ERROR: 4,
            hookenv.CRITICAL: 5}
    if lmap[level] >= lmap[options.get('log_level', 'DEBUG').upper()]:
        hookenv.log('Coordinator: {}'.format(msg), level)


class SimpleCoordinator(BaseCoordinator):
    '''A simple BaseCoordinator that is suitable for almost all cases.

    Only one unit at a time will be granted locks. All requests by that
    unit will be granted. So only one unit may run tasks guarded by a lock,
    and the lock name is irrelevant.
    '''
    def default_grant(self, lock, unit, granted, queue):
        '''Grant locks to only one unit at a time, regardless of the lock name.

        This lets us keep separate locks like join and restart,
        while ensuring the operations do not occur on different nodes
        at the same time.
        '''
        existing_grants = {k: v for k, v in self.grants.items() if v}

        # Return True if this unit has already been granted any lock.
        if existing_grants.get(unit):
            self.msg('Granting {} to {} (existing grants)'.format(lock, unit),
                     hookenv.INFO)
            return True

        # Return False if another unit has been granted any lock.
        if existing_grants:
            self.msg('Not granting {} to {} (locks held by {})'
                     ''.format(lock, unit, ','.join(existing_grants.keys())),
                     hookenv.INFO)
            return False

        # Otherwise, return True if the unit is first in the queue for
        # this named lock.
        if queue[0] == unit:
            self.msg('Granting {} to {} (first in queue)'
                     ''.format(lock, unit), hookenv.INFO)
            return True
        else:
            self.msg('Not granting {} to {} (not first in queue)'
                     ''.format(lock, unit), hookenv.INFO)
            return False

    def msg(self, msg, level=hookenv.DEBUG):
        '''Emit a message.'''
        log(msg, level)

    def _save_state(self):
        # If the leader aquired a lock, and now released it,
        # there may be outstanding requests in the queue from other
        # units. We need to grant them now, as we have no guarantee
        # of another hook running on the leader for some time (until
        # update-status).
        self.handle()
        super(SimpleCoordinator, self)._save_state()


def _instantiate():
    default_name = 'charms.coordinator.SimpleCoordinator'
    full_name = options.get('class', default_name)
    components = full_name.split('.')
    module = '.'.join(components[:-1])
    name = components[-1]

    if not module:
        module = 'charms.coordinator'

    class_ = getattr(importlib.import_module(module), name)

    assert issubclass(class_, BaseCoordinator), \
        '{} is not a BaseCoordinator subclass'.format(full_name)

    try:
        # The Coordinator layer defines its own peer relation, as it
        # can't piggy back on an existing peer relation that may not
        # exist.
        return class_(peer_relation_name='coordinator')
    finally:
        log('Using {} coordinator'.format(full_name), hookenv.DEBUG)


# Instantiate the BaseCoordinator singleton, which installs
# its charmhelpers.core.atstart() hooks.
coordinator = _instantiate()
