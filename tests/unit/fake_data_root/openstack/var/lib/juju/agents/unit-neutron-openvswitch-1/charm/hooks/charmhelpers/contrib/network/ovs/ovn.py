# Copyright 2019 Canonical Ltd
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
import subprocess
import uuid

from . import utils


OVN_RUNDIR = '/var/run/ovn'
OVN_SYSCONFDIR = '/etc/ovn'


def ovn_appctl(target, args, rundir=None, use_ovs_appctl=False):
    """Run ovn/ovs-appctl for target with args and return output.

    :param target: Name of daemon to contact.  Unless target begins with '/',
                   `ovn-appctl` looks for a pidfile and will build the path to
                   a /var/run/ovn/target.pid.ctl for you.
    :type target: str
    :param args: Command and arguments to pass to `ovn-appctl`
    :type args: Tuple[str, ...]
    :param rundir: Override path to sockets
    :type rundir: Optional[str]
    :param use_ovs_appctl: The ``ovn-appctl`` command appeared in OVN 20.03,
                           set this to True to use ``ovs-appctl`` instead.
    :type use_ovs_appctl: bool
    :returns: Output from command
    :rtype: str
    :raises: subprocess.CalledProcessError
    """
    # NOTE(fnordahl): The ovsdb-server processes for the OVN databases use a
    # non-standard naming scheme for their daemon control socket and we need
    # to pass the full path to the socket.
    if target in ('ovnnb_db', 'ovnsb_db',):
        target = os.path.join(rundir or OVN_RUNDIR, target + '.ctl')

    if use_ovs_appctl:
        tool = 'ovs-appctl'
    else:
        tool = 'ovn-appctl'

    return utils._run(tool, '-t', target, *args)


class OVNClusterStatus(object):

    def __init__(self, name, cluster_id, server_id, address, status, role,
                 term, leader, vote, election_timer, log,
                 entries_not_yet_committed, entries_not_yet_applied,
                 connections, servers):
        """Initialize and populate OVNClusterStatus object.

        Use class initializer so we can define types in a compatible manner.

        :param name: Name of schema used for database
        :type name: str
        :param cluster_id: UUID of cluster
        :type cluster_id: uuid.UUID
        :param server_id: UUID of server
        :type server_id: uuid.UUID
        :param address: OVSDB connection method
        :type address: str
        :param status: Status text
        :type status: str
        :param role: Role of server
        :type role: str
        :param term: Election term
        :type term: int
        :param leader: Short form UUID of leader
        :type leader: str
        :param vote: Vote
        :type vote: str
        :param election_timer: Current value of election timer
        :type election_timer: int
        :param log: Log
        :type log: str
        :param entries_not_yet_committed: Entries not yet committed
        :type entries_not_yet_committed: int
        :param entries_not_yet_applied: Entries not yet applied
        :type entries_not_yet_applied: int
        :param connections: Connections
        :type connections: str
        :param servers: Servers in the cluster
            [('0ea6', 'ssl:192.0.2.42:6643')]
        :type servers: List[Tuple[str,str]]
        """
        self.name = name
        self.cluster_id = cluster_id
        self.server_id = server_id
        self.address = address
        self.status = status
        self.role = role
        self.term = term
        self.leader = leader
        self.vote = vote
        self.election_timer = election_timer
        self.log = log
        self.entries_not_yet_committed = entries_not_yet_committed
        self.entries_not_yet_applied = entries_not_yet_applied
        self.connections = connections
        self.servers = servers

    def __eq__(self, other):
        return (
            self.name == other.name and
            self.cluster_id == other.cluster_id and
            self.server_id == other.server_id and
            self.address == other.address and
            self.status == other.status and
            self.role == other.role and
            self.term == other.term and
            self.leader == other.leader and
            self.vote == other.vote and
            self.election_timer == other.election_timer and
            self.log == other.log and
            self.entries_not_yet_committed == other.entries_not_yet_committed and
            self.entries_not_yet_applied == other.entries_not_yet_applied and
            self.connections == other.connections and
            self.servers == other.servers)

    @property
    def is_cluster_leader(self):
        """Retrieve status information from clustered OVSDB.

        :returns: Whether target is cluster leader
        :rtype: bool
        """
        return self.leader == 'self'


def cluster_status(target, schema=None, use_ovs_appctl=False, rundir=None):
    """Retrieve status information from clustered OVSDB.

    :param target: Usually one of 'ovsdb-server', 'ovnnb_db', 'ovnsb_db', can
                   also be full path to control socket.
    :type target: str
    :param schema: Database schema name, deduced from target if not provided
    :type schema: Optional[str]
    :param use_ovs_appctl: The ``ovn-appctl`` command appeared in OVN 20.03,
                           set this to True to use ``ovs-appctl`` instead.
    :type use_ovs_appctl: bool
    :param rundir: Override path to sockets
    :type rundir: Optional[str]
    :returns: cluster status data object
    :rtype: OVNClusterStatus
    :raises: subprocess.CalledProcessError, KeyError, RuntimeError
    """
    schema_map = {
        'ovnnb_db': 'OVN_Northbound',
        'ovnsb_db': 'OVN_Southbound',
    }
    if schema and schema not in schema_map.keys():
        raise RuntimeError('Unknown schema provided: "{}"'.format(schema))

    status = {}
    k = ''
    for line in ovn_appctl(target,
                           ('cluster/status', schema or schema_map[target]),
                           rundir=rundir,
                           use_ovs_appctl=use_ovs_appctl).splitlines():
        if k and line.startswith(' '):
            # there is no key which means this is a instance of a multi-line/
            # multi-value item, populate the List which is already stored under
            # the key.
            if k == 'servers':
                status[k].append(
                    tuple(line.replace(')', '').lstrip().split()[0:4:3]))
            else:
                status[k].append(line.lstrip())
        elif ':' in line:
            # this is a line with a key
            k, v = line.split(':', 1)
            k = k.lower()
            k = k.replace(' ', '_')
            if v:
                # this is a line with both key and value
                if k in ('cluster_id', 'server_id',):
                    v = v.replace('(', '')
                    v = v.replace(')', '')
                    status[k] = tuple(v.split())
                else:
                    status[k] = v.lstrip()
            else:
                # this is a line with only key which means a multi-line/
                # multi-value item.  Store key as List which will be
                # populated on subsequent iterations.
                status[k] = []
    return OVNClusterStatus(
        status['name'],
        uuid.UUID(status['cluster_id'][1]),
        uuid.UUID(status['server_id'][1]),
        status['address'],
        status['status'],
        status['role'],
        int(status['term']),
        status['leader'],
        status['vote'],
        int(status['election_timer']),
        status['log'],
        int(status['entries_not_yet_committed']),
        int(status['entries_not_yet_applied']),
        status['connections'],
        status['servers'])


def is_northd_active():
    """Query `ovn-northd` for active status.

    Note that the active status information for ovn-northd is available for
    OVN 20.03 and onward.

    :returns: True if local `ovn-northd` instance is active, False otherwise
    :rtype: bool
    """
    try:
        for line in ovn_appctl('ovn-northd', ('status',)).splitlines():
            if line.startswith('Status:') and 'active' in line:
                return True
    except subprocess.CalledProcessError:
        pass
    return False
