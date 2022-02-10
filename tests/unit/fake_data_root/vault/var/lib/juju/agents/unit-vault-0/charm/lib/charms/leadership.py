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
from charms.reactive import not_unless


__all__ = ['leader_get', 'leader_set']


@not_unless('leadership.is_leader')
def leader_set(*args, **kw):
    '''Change leadership settings, per charmhelpers.core.hookenv.leader_set.

    Settings may either be passed in as a single dictionary, or using
    keyword arguments. All values must be strings.

    The leadership.set.{key} reactive state will be set while the
    leadership hook environment setting remains set.

    Changed leadership settings will set the leadership.changed.{key}
    and leadership.changed states. These states will remain set until
    the following hook.

    These state changes take effect immediately on the leader, and
    in future hooks run on non-leaders. In this way both leaders and
    non-leaders can share handlers, waiting on these states.
    '''
    if args:
        if len(args) > 1:
            raise TypeError('leader_set() takes 1 positional argument but '
                            '{} were given'.format(len(args)))
        else:
            settings = dict(args[0])
    else:
        settings = {}
    settings.update(kw)
    previous = unitdata.kv().getrange('leadership.settings.', strip=True)

    for key, value in settings.items():
        if value != previous.get(key):
            reactive.set_state('leadership.changed.{}'.format(key))
            reactive.set_state('leadership.changed')
        reactive.helpers.toggle_state('leadership.set.{}'.format(key),
                                      value is not None)
    hookenv.leader_set(settings)
    unitdata.kv().update(settings, prefix='leadership.settings.')


def leader_get(attribute=None):
    '''Return leadership settings, per charmhelpers.core.hookenv.leader_get.'''
    return hookenv.leader_get(attribute)
