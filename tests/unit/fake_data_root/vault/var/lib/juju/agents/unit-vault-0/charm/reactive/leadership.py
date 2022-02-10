# Copyright 2015-2016 Canonical Ltd.
#
# This file is part of the Leadership Layer for Juju.
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
from charmhelpers.core import unitdata

from charms import reactive
from charms.leadership import leader_get, leader_set


__all__ = ['leader_get', 'leader_set']  # Backwards compatibility


def initialize_leadership_state():
    '''Initialize leadership.* states from the hook environment.

    Invoked by hookenv.atstart() so states are available in
    @hook decorated handlers.
    '''
    is_leader = hookenv.is_leader()
    if is_leader:
        hookenv.log('Initializing Leadership Layer (is leader)')
    else:
        hookenv.log('Initializing Leadership Layer (is follower)')

    reactive.helpers.toggle_state('leadership.is_leader', is_leader)

    previous = unitdata.kv().getrange('leadership.settings.', strip=True)
    current = hookenv.leader_get()

    # Handle deletions.
    for key in set(previous.keys()) - set(current.keys()):
        current[key] = None

    any_changed = False
    for key, value in current.items():
        reactive.helpers.toggle_state('leadership.changed.{}'.format(key),
                                      value != previous.get(key))
        if value != previous.get(key):
            any_changed = True
        reactive.helpers.toggle_state('leadership.set.{}'.format(key),
                                      value is not None)
    reactive.helpers.toggle_state('leadership.changed', any_changed)

    unitdata.kv().update(current, prefix='leadership.settings.')


# Per https://github.com/juju-solutions/charms.reactive/issues/33,
# this module may be imported multiple times so ensure the
# initialization hook is only registered once. I have to piggy back
# onto the namespace of a module imported before reactive discovery
# to do this.
if not hasattr(reactive, '_leadership_registered'):
    hookenv.atstart(initialize_leadership_state)
    reactive._leadership_registered = True
