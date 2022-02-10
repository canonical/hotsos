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

import copy
import json
import os
import re
import sys
import subprocess
import glob
import tempfile
import time
import shutil
import socket
import yaml

from collections import OrderedDict, defaultdict

try:
    from croniter import CroniterBadCronError
except ImportError:
    # NOTE(lourot): CroniterBadCronError doesn't exist in croniter
    # 0.3.12 and older, i.e. it doesn't exist in Bionic and older.
    # croniter used to raise a ValueError on these older versions:
    CroniterBadCronError = ValueError
from croniter import croniter

from datetime import datetime

from rabbitmq_context import (
    RabbitMQSSLContext,
    RabbitMQClusterContext,
    RabbitMQEnvContext,
    SSL_CA_FILE,
)

from charmhelpers.contrib.charmsupport import nrpe
import charmhelpers.contrib.openstack.deferred_events as deferred_events
from charmhelpers.core.templating import render

from charmhelpers.contrib.openstack.utils import (
    _determine_os_workload_status,
    get_hostname,
    pause_unit,
    resume_unit,
    is_unit_paused_set,
    pausable_restart_on_change,
)

from charmhelpers.contrib.hahelpers.cluster import (
    distributed_wait,
)

from charmhelpers.core.hookenv import (
    relation_id,
    relation_ids,
    related_units,
    relations_for_id,
    log, ERROR,
    WARNING,
    INFO, DEBUG,
    service_name,
    status_set,
    cached,
    relation_set,
    relation_get,
    application_version_set,
    config,
    is_leader,
    leader_get,
    local_unit,
    charm_dir
)

from charmhelpers.core.host import (
    pwgen,
    mkdir,
    write_file,
    cmp_pkgrevno,
    rsync,
    lsb_release,
    CompareHostReleases,
)

from charmhelpers.contrib.peerstorage import (
    peer_store,
    peer_retrieve
)

from charmhelpers.fetch import (
    apt_pkg,
    apt_update,
    apt_install,
    get_upstream_version,
)

CLUSTER_MODE_KEY = 'cluster-partition-handling'
CLUSTER_MODE_FOR_INSTALL = 'ignore'

PACKAGES = ['rabbitmq-server', 'python3-amqplib', 'lockfile-progs',
            'python3-croniter']

VERSION_PACKAGE = 'rabbitmq-server'

RABBITMQ_CTL = '/usr/sbin/rabbitmqctl'
COOKIE_PATH = '/var/lib/rabbitmq/.erlang.cookie'
ENV_CONF = '/etc/rabbitmq/rabbitmq-env.conf'
RABBITMQ_CONFIG = '/etc/rabbitmq/rabbitmq.config'
RABBITMQ_CONF = '/etc/rabbitmq/rabbitmq.conf'
ENABLED_PLUGINS = '/etc/rabbitmq/enabled_plugins'
RABBIT_USER = 'rabbitmq'
LIB_PATH = '/var/lib/rabbitmq/'
HOSTS_FILE = '/etc/hosts'
NAGIOS_PLUGINS = '/usr/local/lib/nagios/plugins'
SCRIPTS_DIR = '/usr/local/bin'
STATS_CRONFILE = '/etc/cron.d/rabbitmq-stats'
CRONJOB_CMD = ("{schedule} root timeout -k 10s -s SIGINT {timeout} "
               "{command} 2>&1 | logger -p local0.notice\n")

_named_passwd = '/var/lib/charm/{}/{}.passwd'
_local_named_passwd = '/var/lib/charm/{}/{}.local_passwd'


# hook_contexts are used as a convenient mechanism to render templates
# logically, consider building a hook_context for template rendering so
# the charm doesn't concern itself with template specifics etc.

_CONFIG_FILES = OrderedDict([
    (RABBITMQ_CONF, {
        'hook_contexts': [
            RabbitMQSSLContext(),
            RabbitMQClusterContext(),
        ],
        'services': ['rabbitmq-server']
    }),
    (RABBITMQ_CONFIG, {
        'hook_contexts': [
            RabbitMQSSLContext(),
            RabbitMQClusterContext(),
        ],
        'services': ['rabbitmq-server']
    }),
    (ENV_CONF, {
        'hook_contexts': [
            RabbitMQEnvContext(),
        ],
        'services': ['rabbitmq-server']
    }),
    (ENABLED_PLUGINS, {
        'hook_contexts': None,
        'services': ['rabbitmq-server']
    }),
])


def CONFIG_FILES():
    _cfiles = copy.deepcopy(_CONFIG_FILES)
    if cmp_pkgrevno('rabbitmq-server', '3.7') >= 0:
        del _cfiles[RABBITMQ_CONFIG]
    else:
        del _cfiles[RABBITMQ_CONF]
    return _cfiles


class ConfigRenderer(object):
    """
    This class is a generic configuration renderer for
    a given dict mapping configuration files and hook_contexts.
    """
    def __init__(self, config):
        """
        :param config: see CONFIG_FILES
        :type config: dict
        """
        self.config_data = {}

        for config_path, data in config.items():
            hook_contexts = data.get('hook_contexts', None)
            if hook_contexts:
                ctxt = {}
                for svc_context in hook_contexts:
                    ctxt.update(svc_context())
                self.config_data[config_path] = ctxt

    def write(self, config_path):
        data = self.config_data.get(config_path, None)
        if data:
            log("writing config file: %s , data: %s" % (config_path,
                                                        str(data)),
                level='DEBUG')

            render(os.path.basename(config_path), config_path,
                   data, perms=0o644)

    def write_all(self):
        """Write all the defined configuration files"""
        for service in self.config_data.keys():
            self.write(service)

    def complete_contexts(self):
        return []


class RabbitmqError(Exception):
    pass


def run_cmd(cmd):
    """Run provided command and decode the output.

    :param cmd: Command to run
    :type cmd: List[str]
    :returns: output from command
    :rtype: str
    """
    output = subprocess.check_output(cmd)
    output = output.decode('utf-8')
    return output


def rabbit_supports_json():
    """Check if version of rabbit supports json formatted output.

    :returns: If json output is supported.
    :rtype: bool
    """
    return caching_cmp_pkgrevno('rabbitmq-server', '3.8.2') >= 0


@cached
def caching_cmp_pkgrevno(package, revno, pkgcache=None):
    """Compare supplied revno with the revno of the installed package.

    *  1 => Installed revno is greater than supplied arg
    *  0 => Installed revno is the same as supplied arg
    * -1 => Installed revno is less than supplied arg

    :param package: Package to check revno of
    :type package: str
    :param revno: Revision number to compare against
    :type revno: str
    :param pkgcache: Version obj from pkgcache
    :type pkgcache: ubuntu_apt_pkg.Version
    :returns: Whether versions match
    :rtype: int
    """
    return cmp_pkgrevno(package, revno, pkgcache)


def query_rabbit(cmd, raw_processor=None, json_processor=None,
                 binary=RABBITMQ_CTL):
    """Run query against rabbit.

    Run query against rabbit and then run post-query processor on the
    output. If the version of rabbit that is installed supports formatting
    the output in json format then the '--formatter=json' flag is added.

    :param cmd: Query to run
    :type cmd: List[str]
    :param raw_processor: Function to call with command output as the only
                          argument.
    :type raw_processor: Callable
    :param json_processor: Function to call with json loaded output as the only
                          argument.
    :type json_processor: Callable
    :returns: Return processed output from query
    :rtype: ANY
    """
    cmd.insert(0, binary)
    if rabbit_supports_json():
        cmd.append('--formatter=json')
        output = json.loads(run_cmd(cmd))
        if json_processor:
            return json_processor(output)
        else:
            # A processor may not be needed for loaded json.
            return output
    else:
        if raw_processor:
            return raw_processor(run_cmd(cmd))
        else:
            raise NotImplementedError


def list_vhosts():
    """Returns a list of all the available vhosts

    :returns: List of vhosts
    :rtype: [str]
    """
    def _json_processor(output):
        return [ll['name'] for ll in output]

    def _raw_processor(output):
        if '...done' in output:
            return output.split('\n')[1:-2]
        else:
            return output.split('\n')[1:-1]

    try:
        return query_rabbit(
            ['list_vhosts'],
            raw_processor=_raw_processor,
            json_processor=_json_processor)
    except Exception as ex:
        # if no vhosts, just raises an exception
        log(str(ex), level='DEBUG')
        return []


def list_vhost_queue_info(vhost):
    """Provide a list of queue info objects for the given vhost.

    :returns: List of dictionaries of queue information
              eg [{'name': 'queue name', 'messages': 0, 'consumers': 1}, ...]
    :rtype: List[Dict[str, Union[str, int]]]
    :raises: CalledProcessError
    """
    def _raw_processor(output):
        queue_info = []
        if '...done' in output:
            queues = output.split('\n')[1:-2]
        else:
            queues = output.split('\n')[1:-1]

        for queue in queues:
            [qname, qmsgs, qconsumers] = queue.split()
            queue_info.append({
                'name': qname,
                'messages': int(qmsgs),
                'consumers': int(qconsumers)
            })

        return queue_info

    cmd = ['-p', vhost, 'list_queues', 'name', 'messages', 'consumers']
    return query_rabbit(
        cmd,
        raw_processor=_raw_processor)


def list_users():
    """Returns a list of users.

    :returns: List of users
    :rtype: [str]
    """
    def _json_processor(output):
        return [ll['user'] for ll in output]

    def _raw_processor(output):
        lines = output.split('\n')[1:]
        return [line.split('\t')[0] for line in lines]

    return query_rabbit(
        ['list_users'],
        raw_processor=_raw_processor,
        json_processor=_json_processor)


def vhost_queue_info(vhost):
    return list_vhost_queue_info(vhost)


def vhost_exists(vhost):
    return vhost in list_vhosts()


def create_vhost(vhost):
    if vhost_exists(vhost):
        return
    rabbitmqctl('add_vhost', vhost)
    log('Created new vhost (%s).' % vhost)


def user_exists(user):
    return user in list_users()


def create_user(user, password, tags=[]):
    exists = user_exists(user)

    if not exists:
        log('Creating new user (%s).' % user)
        rabbitmqctl('add_user', user, password)

    if 'administrator' in tags:
        log('Granting admin access to {}'.format(user))

    log('Adding tags [{}] to user {}'.format(
        ', '.join(tags),
        user
    ))
    rabbitmqctl('set_user_tags', user, ' '.join(tags))


def grant_permissions(user, vhost):
    """Grant all permissions on a vhost to a user.

    :param user: Name of user to give permissions to.
    :type user: str
    :param vhost: Name of vhost to give permissions on
    :type vhost: str
    """
    log(
        "Granting permissions for user {} on vhost {}".format(user, vhost),
        level='DEBUG')
    log("Granting permissions", level='DEBUG')
    rabbitmqctl('set_permissions', '-p',
                vhost, user, '.*', '.*', '.*')


def set_policy(vhost, policy_name, match, value):
    log("setting policy", level='DEBUG')
    rabbitmqctl('set_policy', '-p', vhost,
                policy_name, match, value)


def set_ha_mode(vhost, mode, params=None, sync_mode='automatic'):
    """Valid mode values:

      * 'all': Queue is mirrored across all nodes in the cluster. When a new
         node is added to the cluster, the queue will be mirrored to that node.
      * 'exactly': Queue is mirrored to count nodes in the cluster.
      * 'nodes': Queue is mirrored to the nodes listed in node names

    More details at http://www.rabbitmq.com./ha.html

    :param vhost: virtual host name
    :param mode: ha mode
    :param params: values to pass to the policy, possible values depend on the
                   mode chosen.
    :param sync_mode: when `mode` is 'exactly' this used to indicate how the
                      sync has to be done
                      http://www.rabbitmq.com./ha.html#eager-synchronisation
    """

    if caching_cmp_pkgrevno('rabbitmq-server', '3.0.0') < 0:
        log(("Mirroring queues cannot be enabled, only supported "
             "in rabbitmq-server >= 3.0"), level=WARNING)
        log(("More information at http://www.rabbitmq.com/blog/"
             "2012/11/19/breaking-things-with-rabbitmq-3-0"), level='INFO')
        return

    if mode == 'all':
        definition = {
            "ha-mode": "all",
            "ha-sync-mode": sync_mode}
    elif mode == 'exactly':
        definition = {
            "ha-mode": "exactly",
            "ha-params": params,
            "ha-sync-mode": sync_mode}
    elif mode == 'nodes':
        definition = {
            "ha-mode": "nodes",
            "ha-params": params,
            "ha-sync-mode": sync_mode}
    else:
        raise RabbitmqError(("Unknown mode '%s', known modes: "
                             "all, exactly, nodes"))

    log("Setting HA policy to vhost '%s'" % vhost, level='INFO')
    set_policy(vhost, 'HA', r'^(?!amq\.).*', json.dumps(definition))


def clear_ha_mode(vhost, name='HA', force=False):
    """
    Clear policy from the `vhost` by `name`
    """
    if cmp_pkgrevno('rabbitmq-server', '3.0.0') < 0:
        log(("Mirroring queues not supported "
             "in rabbitmq-server >= 3.0"), level=WARNING)
        log(("More information at http://www.rabbitmq.com/blog/"
             "2012/11/19/breaking-things-with-rabbitmq-3-0"), level='INFO')
        return

    log("Clearing '%s' policy from vhost '%s'" % (name, vhost), level='INFO')
    try:
        rabbitmqctl('clear_policy', '-p', vhost, name)
    except subprocess.CalledProcessError as ex:
        if not force:
            raise ex


def set_all_mirroring_queues(enable):
    """
    :param enable: if True then enable mirroring queue for all the vhosts,
                   otherwise the HA policy is removed
    """
    if cmp_pkgrevno('rabbitmq-server', '3.0.0') < 0:
        log(("Mirroring queues not supported "
             "in rabbitmq-server >= 3.0"), level=WARNING)
        log(("More information at http://www.rabbitmq.com/blog/"
             "2012/11/19/breaking-things-with-rabbitmq-3-0"), level='INFO')
        return

    if enable:
        status_set('active', 'Enabling queue mirroring')
    else:
        status_set('active', 'Disabling queue mirroring')

    for vhost in list_vhosts():
        if enable:
            set_ha_mode(vhost, 'all')
        else:
            clear_ha_mode(vhost, force=True)


def rabbitmqctl(action, *args):
    ''' Run rabbitmqctl with action and args. This function uses
        subprocess.check_call. For uses that need check_output
        use a direct subprocess call or rabbitmqctl_normalized_output
        function.
     '''
    # NOTE(lourot): before rabbitmq-server 3.8 (focal),
    # `rabbitmqctl wait <pidfile>` doesn't have a `--timeout` option and thus
    # may hang forever and needs to be wrapped in
    # `timeout 180 rabbitmqctl wait <pidfile>`.
    # Since 3.8 there is a `--timeout` option, whose default is 10 seconds. [1]
    #
    # [1]: https://github.com/rabbitmq/rabbitmq-server/commit/3dd58ae1
    WAIT_TIMEOUT_SECONDS = 180
    focal_or_newer = rabbitmq_version_newer_or_equal('3.8')

    cmd = []
    if 'wait' in action and not focal_or_newer:
        cmd.extend(['timeout', str(WAIT_TIMEOUT_SECONDS)])
    cmd.extend([RABBITMQ_CTL, action])
    for arg in args:
        cmd.append(arg)
    if 'wait' in action and focal_or_newer:
        cmd.extend(['--timeout', str(WAIT_TIMEOUT_SECONDS)])
    log("Running {}".format(cmd), 'DEBUG')
    subprocess.check_call(cmd)


def configure_notification_ttl(vhost, ttl=3600000):
    ''' Configure 1h minute TTL for notfication topics in the provided vhost
        This is a workaround for filling notification queues in OpenStack
        until a more general service discovery mechanism exists so that
        notifications can be enabled/disabled on each individual service.
    '''
    rabbitmqctl('set_policy',
                'TTL', '^(versioned_)?notifications.*',
                '{{"message-ttl":{ttl}}}'.format(ttl=ttl),
                '--priority', '1',
                '--apply-to', 'queues',
                '-p', vhost)


def configure_ttl(vhost, ttlname, ttlreg, ttl):
    ''' Some topic queues like in heat also need to set TTL, see lp:1925436
        Configure TTL for heat topics in the provided vhost, this is a
        workaround for filling heat queues and for future other queues
    '''
    log('configure_ttl: ttlname={} ttlreg={} ttl={}'.format(
        ttlname, ttlreg, ttl), INFO)
    if not all([ttlname, ttlreg, ttl]):
        return
    rabbitmqctl('set_policy',
                '{ttlname}'.format(ttlname=ttlname),
                '"{ttlreg}"'.format(ttlreg=ttlreg),
                '{{"expires":{ttl}}}'.format(ttl=ttl),
                '--priority', '1',
                '--apply-to', 'queues',
                '-p', vhost)


def rabbitmqctl_normalized_output(*args):
    ''' Run rabbitmqctl with args. Normalize output by removing
        whitespace and return it to caller for further processing.
    '''
    cmd = [RABBITMQ_CTL]
    cmd.extend(args)
    out = (subprocess
           .check_output(cmd, stderr=subprocess.STDOUT)
           .decode('utf-8'))

    # Output is in Erlang External Term Format (ETF).  The amount of whitespace
    # (including newlines in the middle of data structures) in the output
    # depends on the data presented.  ETF resembles JSON, but it is not.
    # Writing our own parser is a bit out of scope, enabling management-plugin
    # to use REST interface might be overkill at this stage.
    #
    # Removing whitespace will let our simple pattern matching work and is a
    # compromise.
    return out.translate(str.maketrans(dict.fromkeys(' \t\n')))


def wait_app():
    ''' Wait until rabbitmq has fully started '''
    run_dir = '/var/run/rabbitmq/'
    if os.path.isdir(run_dir):
        pid_file = run_dir + 'pid'
    else:
        pid_file = '/var/lib/rabbitmq/mnesia/rabbit@' \
                   + socket.gethostname() + '.pid'
    log('Waiting for rabbitmq app to start: {}'.format(pid_file), DEBUG)
    try:
        rabbitmqctl('wait', pid_file)
        log('Confirmed rabbitmq app is running', DEBUG)
        return True
    except subprocess.CalledProcessError as ex:
        status_set('blocked', 'RabbitMQ failed to start')
        try:
            status_cmd = ['rabbitmqctl', 'status']
            log(subprocess.check_output(status_cmd).decode('utf-8'), DEBUG)
        except Exception:
            pass
        raise ex


def cluster_wait():
    ''' Wait for operations based on modulo distribution

    Use the distributed_wait function to determine how long to wait before
    running an operation like restart or cluster join. By setting modulo to
    the exact number of nodes in the cluster we get serial operations.

    Check for explicit configuration parameters for modulo distribution.
    The config setting modulo-nodes has first priority. If modulo-nodes is not
    set, check min-cluster-size. Finally, if neither value is set, determine
    how many peers there are from the cluster relation.

    @side_effect: distributed_wait is called which calls time.sleep()
    @return: None
    '''
    wait = config('known-wait')
    if config('modulo-nodes') is not None:
        # modulo-nodes has first priority
        num_nodes = config('modulo-nodes')
    elif config('min-cluster-size'):
        # min-cluster-size is consulted next
        num_nodes = config('min-cluster-size')
    else:
        # If nothing explicit is configured, determine cluster size based on
        # peer relations
        num_nodes = 1
        for rid in relation_ids('cluster'):
            num_nodes += len(related_units(rid))
    distributed_wait(modulo=num_nodes, wait=wait)


def start_app():
    ''' Start the rabbitmq app and wait until it is fully started '''
    status_set('maintenance', 'Starting rabbitmq application')
    rabbitmqctl('start_app')
    wait_app()


def join_cluster(node):
    ''' Join cluster with node '''
    if cmp_pkgrevno('rabbitmq-server', '3.0.1') >= 0:
        cluster_cmd = 'join_cluster'
    else:
        cluster_cmd = 'cluster'
    status_set('maintenance',
               'Clustering with remote rabbit host (%s).' % node)
    rabbitmqctl('stop_app')
    # Intentionally using check_output so we can see rabbitmqctl error
    # message if it fails
    cmd = [RABBITMQ_CTL, cluster_cmd, node]
    subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    start_app()
    log('Host clustered with %s.' % node, 'INFO')


def cluster_with():
    if is_unit_paused_set():
        log("Do not run cluster_with while unit is paused", "WARNING")
        return

    log('Clustering with new node')

    # check the leader and try to cluster with it
    node = leader_node()
    if node:
        if node in running_nodes():
            log('Host already clustered with %s.' % node)

            cluster_rid = relation_id('cluster', local_unit())
            is_clustered = relation_get(attribute='clustered',
                                        rid=cluster_rid,
                                        unit=local_unit())

            log('am I clustered?: %s' % bool(is_clustered), level=DEBUG)
            if not is_clustered:
                # NOTE(freyes): this node needs to be marked as clustered, it's
                # part of the cluster according to 'rabbitmqctl cluster_status'
                # (LP: #1691510)
                relation_set(relation_id=cluster_rid,
                             clustered=get_unit_hostname(),
                             timestamp=time.time())

            return False
        # NOTE: The primary problem rabbitmq has clustering is when
        # more than one node attempts to cluster at the same time.
        # The asynchronous nature of hook firing nearly guarantees
        # this. Using cluster_wait based on modulo_distribution
        cluster_wait()
        try:
            join_cluster(node)
            # NOTE: toggle the cluster relation to ensure that any peers
            #       already clustered re-assess status correctly
            relation_set(clustered=get_unit_hostname(), timestamp=time.time())
            return True
        except subprocess.CalledProcessError as e:
            status_set('blocked', 'Failed to cluster with %s. Exception: %s'
                       % (node, e))
            start_app()
    else:
        status_set('waiting', 'Leader not available for clustering')
        return False

    return False


def check_cluster_memberships():
    """Check for departed nodes.

    Iterate over RabbitMQ node list, compare it to charm cluster relationships,
    and notify about any nodes previously abruptly removed from the cluster.

    :returns: String node name or None
    :rtype: Union[str, None]
    """
    for rid in relation_ids('cluster'):
        for node in nodes():
            if not any(rel.get('clustered', None) == node.split('@')[1]
                       for rel in relations_for_id(relid=rid)) and \
                    node not in running_nodes():
                log("check_cluster_memberships(): '{}' in nodes but not in "
                    "charm relations or running_nodes."
                    .format(node), level=DEBUG)
                return node


def leave_cluster():
    ''' Leave cluster gracefully '''
    try:
        rabbitmqctl('stop_app')
        rabbitmqctl('reset')
        start_app()
        log('Successfully left cluster gracefully.')
    except Exception:
        # error, no nodes available for clustering
        log('Cannot leave cluster, we might be the last disc-node in the '
            'cluster.', level=ERROR)
        raise


def get_plugin_manager():
    """Find the path to the executable for managing plugins.

    :returns: Path to rabbitmq-plugins executable
    :rtype: str
    """
    # At version 3.8.2, only /sbin/rabbitmq-plugins can enable plugin correctly
    if os.path.exists("/sbin/rabbitmq-plugins"):
        return '/sbin/rabbitmq-plugins'
    else:
        return glob.glob(
            '/usr/lib/rabbitmq/lib/rabbitmq_server-*/sbin/rabbitmq-plugins')[0]


def _manage_plugin(plugin, action):
    os.environ['HOME'] = '/root'
    plugin_manager = get_plugin_manager()
    subprocess.check_call([plugin_manager, action, plugin])


def enable_plugin(plugin):
    _manage_plugin(plugin, 'enable')


def disable_plugin(plugin):
    _manage_plugin(plugin, 'disable')


def get_managment_port():
    if rabbitmq_version_newer_or_equal('3'):
        return 15672
    else:
        return 55672


def execute(cmd, die=False, echo=False):
    """ Executes a command

    if die=True, script will exit(1) if command does not return 0
    if echo=True, output of command will be printed to stdout

    returns a tuple: (stdout, stderr, return code)
    """
    p = subprocess.Popen(cmd.split(" "),
                         stdout=subprocess.PIPE,
                         stdin=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout = ""
    stderr = ""

    def print_line(ll):
        if echo:
            print(ll.strip('\n'))
            sys.stdout.flush()

    for ll in iter(p.stdout.readline, ''):
        print_line(ll)
        stdout += ll
    for ll in iter(p.stderr.readline, ''):
        print_line(ll)
        stderr += ll

    p.communicate()
    rc = p.returncode

    if die and rc != 0:
        log("command %s return non-zero." % cmd, level=ERROR)
    return (stdout, stderr, rc)


def get_rabbit_password_on_disk(username, password=None, local=False):
    ''' Retrieve, generate or store a rabbit password for
    the provided username on disk'''
    if local:
        _passwd_file = _local_named_passwd.format(service_name(), username)
    else:
        _passwd_file = _named_passwd.format(service_name(), username)

    _password = None
    if os.path.exists(_passwd_file):
        with open(_passwd_file, 'r') as passwd:
            _password = passwd.read().strip()
    else:
        mkdir(os.path.dirname(_passwd_file), owner=RABBIT_USER,
              group=RABBIT_USER, perms=0o775)
        os.chmod(os.path.dirname(_passwd_file), 0o775)
        _password = password or pwgen(length=64)
        write_file(_passwd_file, _password, owner=RABBIT_USER,
                   group=RABBIT_USER, perms=0o660)

    return _password


def migrate_passwords_to_peer_relation():
    '''Migrate any passwords storage on disk to cluster peer relation'''
    for f in glob.glob('/var/lib/charm/{}/*.passwd'.format(service_name())):
        _key = os.path.basename(f)
        with open(f, 'r') as passwd:
            _value = passwd.read().strip()
        try:
            peer_store(_key, _value)
            os.unlink(f)
        except ValueError:
            # NOTE cluster relation not yet ready - skip for now
            pass


def get_rabbit_password(username, password=None, local=False):
    ''' Retrieve, generate or store a rabbit password for
    the provided username using peer relation cluster'''
    if local:
        return get_rabbit_password_on_disk(username, password, local)
    else:
        migrate_passwords_to_peer_relation()
        _key = '{}.passwd'.format(username)
        try:
            _password = peer_retrieve(_key)
            if _password is None:
                _password = password or pwgen(length=64)
                peer_store(_key, _password)
        except ValueError:
            # cluster relation is not yet started, use on-disk
            _password = get_rabbit_password_on_disk(username, password)
        return _password


def update_hosts_file(map):
    """Rabbitmq does not currently like ipv6 addresses so we need to use dns
    names instead. In order to make them resolvable we ensure they are  in
    /etc/hosts.

    """
    with open(HOSTS_FILE, 'r') as hosts:
        lines = hosts.readlines()

    log("Updating hosts file with: %s (current: %s)" % (map, lines),
        level=INFO)

    newlines = []
    for ip, hostname in map.items():
        if not ip or not hostname:
            continue

        keepers = []
        for line in lines:
            _line = line.split()
            if len(line) < 2 or not (_line[0] == ip or hostname in _line[1:]):
                keepers.append(line)
            else:
                log("Removing line '%s' from hosts file" % (line))

        lines = keepers
        newlines.append("%s %s\n" % (ip, hostname))

    lines += newlines

    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        with open(tmpfile.name, 'w') as hosts:
            for line in lines:
                hosts.write(line)

    shutil.move(tmpfile.name, HOSTS_FILE)
    os.chmod(HOSTS_FILE, 0o644)


def restart_map():
    '''Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = []
    for f, ctxt in _CONFIG_FILES.items():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map.append((f, svcs))
    return OrderedDict(_map)


def services():
    ''' Returns a list of services associate with this charm '''
    _services = []
    for v in restart_map().values():
        _services = _services + v
    return list(set(_services))


def get_cluster_status(cmd_timeout=None):
    """Raturn rabbit cluster status

    :param cmd_timeout: How long to give the command to complete.
    :type cmd_timeout: int
    :returns: Rabbitmq cluster status
    :rtype: dict
    :raises: NotImplementedError, subprocess.TimeoutExpired,
    """
    if caching_cmp_pkgrevno('rabbitmq-server', '3.8.2') >= 0:
        cmd = [RABBITMQ_CTL, 'cluster_status', '--formatter=json']
        output = subprocess.check_output(
            cmd,
            timeout=cmd_timeout).decode('utf-8')
        return json.loads(output)
    else:
        # rabbitmqctl has not implemented the formatter option.
        raise NotImplementedError


@cached
def nodes(get_running=False):
    ''' Get list of nodes registered in the RabbitMQ cluster '''
    # NOTE(ajkavanagh): In focal and above, rabbitmq-server now has a
    # --formatter option.
    try:
        status = get_cluster_status()
        if get_running:
            return status['running_nodes']
        return status['disk_nodes'] + status['ram_nodes']
    except NotImplementedError:
        out = rabbitmqctl_normalized_output('cluster_status')
        cluster_status = {}
        for m in re.finditer(r"{([^,]+),(?!\[{)\[([^\]]*)", out):
            state = m.group(1)
            items = m.group(2).split(',')
            items = [x.replace("'", '').strip() for x in items]
            cluster_status.update({state: items})

        if get_running:
            return cluster_status.get('running_nodes', [])

        return cluster_status.get('disc', []) + cluster_status.get('ram', [])


@cached
def is_partitioned():
    """Check whether rabbitmq cluster is partitioned.

    :returns: Whether cluster is partitioned
    :rtype: bool
    :raises: NotImplementedError, subprocess.TimeoutExpired,
    """
    status = get_cluster_status(cmd_timeout=60)
    return status.get('partitions') != {}


@cached
def running_nodes():
    ''' Determine the current set of running nodes in the RabbitMQ cluster '''
    return nodes(get_running=True)


@cached
def leader_node():
    ''' Provide the leader node for clustering

    @returns leader node's hostname or None
    '''
    # Each rabbitmq node should join_cluster with the leader
    # to avoid split-brain clusters.
    try:
        leader_node_hostname = peer_retrieve('leader_node_hostname')
    except ValueError:
        # This is a single unit
        return None
    if leader_node_hostname:
        return "rabbit@" + leader_node_hostname
    else:
        return None


def get_node_hostname(ip_addr):
    ''' Resolve IP address to hostname '''
    try:
        nodename = get_hostname(ip_addr, fqdn=False)
    except Exception:
        log('Cannot resolve hostname for %s using DNS servers' % ip_addr,
            level=WARNING)
        log('Falling back to use socket.gethostname()',
            level=WARNING)
        # If the private-address is not resolvable using DNS
        # then use the current hostname
        nodename = socket.gethostname()
    log('local nodename: %s' % nodename, level=INFO)
    return nodename


@cached
def clustered():
    ''' Determine whether local rabbitmq-server is clustered '''
    # NOTE: A rabbitmq node can only join a cluster once.
    # Simply checking for more than one running node tells us
    # if this unit is in a cluster.
    if len(running_nodes()) > 1:
        return True
    else:
        return False


def assess_cluster_status(*args):
    ''' Assess the status for the current running unit '''
    if is_unit_paused_set():
        return "maintenance", "Paused"

    # NOTE: ensure rabbitmq is actually installed before doing
    #       any checks
    if not rabbitmq_is_installed():
        return 'waiting', 'RabbitMQ is not yet installed'

    # Sufficient peers
    if not is_sufficient_peers():
        return 'waiting', ("Waiting for all {} peers to complete the "
                           "cluster.".format(config('min-cluster-size')))
    # Clustering Check
    peer_ids = relation_ids('cluster')
    if peer_ids and len(related_units(peer_ids[0])):
        if not clustered():
            return 'waiting', 'Unit has peers, but RabbitMQ not clustered'

    # Departed nodes
    departed_node = check_cluster_memberships()
    if departed_node:
        return (
            'blocked',
            'Node {} in the cluster but not running. If it is a departed '
            'node, remove with `forget-cluster-node` action'
            .format(departed_node))

    # Check if cluster is partitioned
    try:
        if peer_ids and len(related_units(peer_ids[0])) and is_partitioned():
            return ('blocked', 'RabbitMQ is partitioned')
    except (subprocess.TimeoutExpired, NotImplementedError):
        pass

    # General status check
    if not wait_app():
        return (
            'blocked', 'Unable to determine if the rabbitmq service is up')

    if leader_get(CLUSTER_MODE_KEY) != config(CLUSTER_MODE_KEY):
        return (
            'waiting',
            'Not reached target {} mode'.format(CLUSTER_MODE_KEY))

    # we're active - so just return the 'active' state, but if 'active'
    # is returned, then it is ignored by the assess_status system.
    return 'active', "message is ignored"


def restart_on_change(restart_map, stopstart=False):
    """Restart services based on configuration files changing

    This function is used a decorator, for example::

        @restart_on_change({
            '/etc/apache/sites-enabled/*': [ 'apache2' ]
            })
        def config_changed():
            pass  # your code here

    In this example the apache2 service would be
    restarted if any file matching the pattern got changed, created
    or removed. Standard wildcards are supported, see documentation
    for the 'glob' module for more information.
    """
    return pausable_restart_on_change(
        restart_map,
        stopstart=stopstart,
        pre_restarts_wait_f=cluster_wait,
        can_restart_now_f=deferred_events.check_and_record_restart_request,
        post_svc_restart_f=deferred_events.process_svc_restart
    )


def assess_status(configs):
    """Assess status of current unit
    Decides what the state of the unit should be based on the current
    configuration.
    SIDE EFFECT: calls set_os_workload_status(...) which sets the workload
    status of the unit.
    Also calls status_set(...) directly if paused state isn't complete.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    deferred_events.check_restart_timestamps()
    assess_status_func(configs)()
    rmq_version = get_upstream_version(VERSION_PACKAGE)
    if rmq_version:
        application_version_set(rmq_version)


def assess_status_func(configs):
    """Helper function to create the function that will assess_status() for
    the unit.
    Uses charmhelpers.contrib.openstack.utils.make_assess_status_func() to
    create the appropriate status function and then returns it.
    Used directly by assess_status() and also for pausing and resuming
    the unit.

    NOTE(ajkavanagh) ports are not checked due to race hazards with services
    that don't behave sychronously w.r.t their service scripts.  e.g.
    apache2.
    @param configs: a templating.OSConfigRenderer() object
    @return f() -> None : a function that assesses the unit's workload status
    """
    def _assess_status_func():
        state, message = _determine_os_workload_status(
            configs, {},
            charm_func=assess_cluster_status,
            services=services(), ports=None)
        if state == 'active' and clustered():
            message = 'Unit is ready and clustered'
        # Remind the administrator cluster_series_upgrading is set.
        # If the cluster has completed the series upgrade, run the
        # complete-cluster-series-upgrade action to clear this setting.
        if leader_get('cluster_series_upgrading'):
            message += (", run complete-cluster-series-upgrade when the "
                        "cluster has completed its upgrade")
            # Edge case when the first rabbitmq unit is upgraded it will show
            # waiting for peers. Force "active" workload state for various
            # testing suites like zaza to recognize a successful series upgrade
            # of the first unit.
            if state == "waiting":
                state = "active"

        # Validate that the cron schedule for nrpe status checks is correct. An
        # invalid cron schedule will not prevent the rabbitmq service from
        # running but may cause problems with nrpe checks.
        schedule = config('stats_cron_schedule')
        if schedule and not is_cron_schedule_valid(schedule):
            message += ". stats_cron_schedule is invalid"

        # Deferred restarts should be managed by _determine_os_workload_status
        # but rabbits wlm code needs refactoring to make it consistent with
        # other charms as any message returned by _determine_os_workload_status
        # is currently dropped on the floor if: state == 'active'
        events = defaultdict(set)
        for e in deferred_events.get_deferred_events():
            events[e.action].add(e.service)
        for action, svcs in events.items():
            svc_msg = "Services queued for {}: {}".format(
                action, ', '.join(sorted(svcs)))
            message = "{}. {}".format(message, svc_msg)
        deferred_hooks = deferred_events.get_deferred_hooks()
        if deferred_hooks:
            svc_msg = "Hooks skipped due to disabled auto restarts: {}".format(
                ', '.join(sorted(deferred_hooks)))
            message = "{}. {}".format(message, svc_msg)

        status_set(state, message)

    return _assess_status_func


def pause_unit_helper(configs):
    """Helper function to pause a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.pause_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(pause_unit, configs)


def resume_unit_helper(configs):
    """Helper function to resume a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.resume_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(resume_unit, configs)


def _pause_resume_helper(f, configs):
    """Helper function that uses the make_assess_status_func(...) from
    charmhelpers.contrib.openstack.utils to create an assess_status(...)
    function that can be used with the pause/resume of the unit
    @param f: the function to be used with the assess_status(...) function
    @returns None - this function is executed for its side-effect
    """
    # TODO(ajkavanagh) - ports= has been left off because of the race hazard
    # that exists due to service_start()
    f(assess_status_func(configs),
      services=services(),
      ports=None)


def get_unit_hostname():
    """Return this unit's hostname.

    @returns hostname
    """
    return socket.gethostname()


def is_sufficient_peers():
    """Sufficient number of expected peers to build a complete cluster

    If min-cluster-size has been provided, check that we have sufficient
    number of peers who have presented a hostname for a complete cluster.

    If not defined assume a single unit.

    @returns boolean
    """
    min_size = config('min-cluster-size')
    if min_size:
        log("Checking for minimum of {} peer units".format(min_size),
            level=DEBUG)

        # Include this unit
        units = 1
        for rid in relation_ids('cluster'):
            for unit in related_units(rid):
                if relation_get(attribute='hostname',
                                rid=rid, unit=unit):
                    units += 1

        if units < min_size:
            log("Insufficient number of peer units to form cluster "
                "(expected=%s, got=%s)" % (min_size, units), level=INFO)
            return False
        else:
            log("Sufficient number of peer units to form cluster {}"
                "".format(min_size), level=DEBUG)
            return True
    else:
        log("min-cluster-size is not defined, race conditions may occur if "
            "this is not a single unit deployment.", level=WARNING)
        return True


def rabbitmq_is_installed():
    """Determine if rabbitmq is installed

    @returns boolean
    """
    return os.path.exists(RABBITMQ_CTL)


def cluster_ready():
    """Determine if each node in the cluster is ready and the cluster is
    complete with the expected number of peers.

    Once cluster_ready returns True it is safe to execute client relation
    hooks. Having min-cluster-size set will guarantee cluster_ready will not
    return True until the expected number of peers are clustered and ready.

    If min-cluster-size is not set it must assume the cluster is ready in order
    to allow for single unit deployments.

    @returns boolean
    """
    min_size = config('min-cluster-size')
    units = 1
    for rid in relation_ids('cluster'):
        units += len(related_units(rid))
    if not min_size:
        min_size = units

    if not is_sufficient_peers():
        return False
    elif min_size > 1:
        if not clustered():
            return False
        clustered_units = 1
        for rid in relation_ids('cluster'):
            for remote_unit in related_units(rid):
                if not relation_get(attribute='clustered',
                                    rid=rid,
                                    unit=remote_unit):
                    log("{} is not yet clustered".format(remote_unit),
                        DEBUG)
                    return False
                else:
                    clustered_units += 1
        if clustered_units < min_size:
            log("Fewer than minimum cluster size:{} rabbit units reporting "
                "clustered".format(min_size),
                DEBUG)
            return False
        else:
            log("All {} rabbit units reporting clustered"
                "".format(min_size),
                DEBUG)
            return True

    log("Must assume this is a single unit returning 'cluster' ready", DEBUG)
    return True


def client_node_is_ready():
    """Determine if the leader node has set amqp client data

    @returns boolean
    """
    # Bail if this unit is paused
    if is_unit_paused_set():
        return False
    for rid in relation_ids('amqp'):
        if leader_get(attribute='{}_password'.format(rid)):
            return True
    return False


def leader_node_is_ready():
    """Determine if the leader node is ready to handle client relationship
    hooks.

    IFF rabbit is not paused, is installed, this is the leader node and the
    cluster is complete.

    @returns boolean
    """
    # Paused check must run before other checks
    # Bail if this unit is paused
    if is_unit_paused_set():
        return False
    return (rabbitmq_is_installed() and
            is_leader() and
            cluster_ready())


def archive_upgrade_available():
    """Check if the change in sources.list would warrant running
    apt-get update/upgrade

    @returns boolean:
        True: the "source" had changed, so upgrade is available
        False: the "source" had not changed, no upgrade needed
    """
    log('checking if upgrade is available', DEBUG)

    c = config()
    old_source = c.previous('source')
    log('Previous "source" config options was: {}'.format(old_source), DEBUG)
    new_source = c['source']
    log('Current "source" config options is: {}'.format(new_source), DEBUG)

    if old_source != new_source:
        log('The "source" config option change warrants the upgrade.', INFO)

    return old_source != new_source


def install_or_upgrade_packages():
    """Run apt-get update/upgrade mantra.
    This is called from either install hook, or from config-changed,
    if upgrade is warranted
    """
    status_set('maintenance', 'Installing/upgrading RabbitMQ packages')
    apt_update(fatal=True)
    apt_install(PACKAGES, fatal=True)


def remove_file(path):
    """Delete the file or skip it if not exist.

    :param path: the file to delete
    :type path: str
    """
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.exists(path):
        log('{} path is not file'.format(path), level='ERROR')
    else:
        log('{} file does not exist'.format(path), level='DEBUG')


def management_plugin_enabled():
    """Check if management plugin should be enabled.

    :returns: Whether anagement plugin should be enabled
    :rtype: bool
    """
    _release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(_release) < "bionic":
        return False
    else:
        return config('management_plugin') is True


def sync_nrpe_files():
    """Sync all NRPE-related files.

    Copy all the custom NRPE scripts and create the cron file to run
    rabbitmq stats collection
    """
    if not os.path.exists(NAGIOS_PLUGINS):
        os.makedirs(NAGIOS_PLUGINS, exist_ok=True)

    if config('ssl'):
        rsync(os.path.join(charm_dir(), 'files', 'check_rabbitmq.py'),
              os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq.py'))
    if config('queue_thresholds') and config('stats_cron_schedule'):
        rsync(os.path.join(charm_dir(), 'files', 'check_rabbitmq_queues.py'),
              os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq_queues.py'))
    if management_plugin_enabled():
        rsync(os.path.join(charm_dir(), 'files', 'check_rabbitmq_cluster.py'),
              os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq_cluster.py'))

    if config('stats_cron_schedule'):
        rsync(os.path.join(charm_dir(), 'files', 'collect_rabbitmq_stats.sh'),
              os.path.join(SCRIPTS_DIR, 'collect_rabbitmq_stats.sh'))
        cronjob = CRONJOB_CMD.format(
            schedule=config('stats_cron_schedule'),
            timeout=config('cron-timeout'),
            command=os.path.join(SCRIPTS_DIR, 'collect_rabbitmq_stats.sh'))
        write_file(STATS_CRONFILE, cronjob)


def remove_nrpe_files():
    """Remove the cron file and all the custom NRPE scripts."""
    if not config('stats_cron_schedule'):
        # These scripts are redundant if the value `stats_cron_schedule`
        # isn't in the config
        remove_file(STATS_CRONFILE)
        remove_file(os.path.join(SCRIPTS_DIR, 'collect_rabbitmq_stats.sh'))

    if not config('ssl'):
        # This script is redundant if the value `ssl` isn't in the config
        remove_file(os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq.py'))

    if not config('queue_thresholds') or not config('stats_cron_schedule'):
        # This script is redundant if the value `queue_thresholds` or
        # `stats_cron_schedule` isn't in the config
        remove_file(os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq_queues.py'))

    if not management_plugin_enabled():
        # This script is redundant if the value `management_plugin` isn't
        # in the config
        remove_file(os.path.join(NAGIOS_PLUGINS, 'check_rabbitmq_cluster.py'))


def get_nrpe_credentials():
    """Get the NRPE hostname, unit and user details.

    :returns: (hostname, unit, vhosts, user, password)
    :rtype: Tuple[str, str, List[Dict[str, str]], str, str]
    """
    # Find out if nrpe set nagios_hostname
    hostname = nrpe.get_nagios_hostname()
    unit = nrpe.get_nagios_unit_name()

    # create unique user and vhost for each unit
    current_unit = local_unit().replace('/', '-')
    user = 'nagios-{}'.format(current_unit)
    vhosts = [{'vhost': user, 'shortname': RABBIT_USER}]
    password = get_rabbit_password(user, local=True)
    create_user(user, password, ['monitoring'])

    if config('check-vhosts'):
        for other_vhost in config('check-vhosts').split(' '):
            if other_vhost:
                item = {'vhost': other_vhost,
                        'shortname': 'rabbit_{}'.format(other_vhost)}
                vhosts.append(item)

    return hostname, unit, vhosts, user, password


def nrpe_update_vhost_check(nrpe_compat, unit, user, password, vhost):
    """Add/Remove the RabbitMQ non-SSL check

    If the SSL is set to `off` or `on`, it will add the non-SSL RabbitMQ check,
    otherwise it will remove it.

    :param nrpe_compat: the NRPE class object
    :type: nrpe.NRPE
    :param unit: NRPE unit
    :type: str
    :param user: username of NRPE user
    :type: str
    :param password: password of NRPE user
    :type: str
    :param vhost: dictionary with vhost and shortname
    :type: Dict[str, str]
    """
    ssl_config = config('ssl') or ''
    if ssl_config.lower() in ['off', 'on']:
        log('Adding rabbitmq non-SSL check for {}'.format(vhost['vhost']),
            level=DEBUG)
        nrpe_compat.add_check(
            shortname=vhost['shortname'],
            description='Check RabbitMQ {} {}'.format(unit, vhost['vhost']),
            check_cmd='{}/check_rabbitmq.py --user {} --password {} '
                      '--vhost {}'.format(
                          NAGIOS_PLUGINS, user, password, vhost['vhost']))
    else:
        log('Removing rabbitmq non-SSL check for {}'.format(vhost['vhost']),
            level=DEBUG)
        nrpe_compat.remove_check(
            shortname=vhost['shortname'],
            description='Remove check RabbitMQ {} {}'.format(
                unit, vhost['vhost']),
            check_cmd='{}/check_rabbitmq.py'.format(NAGIOS_PLUGINS))


def nrpe_update_vhost_ssl_check(nrpe_compat, unit, user, password, vhost):
    """Add/Remove the RabbitMQ SSL check

    If the SSL is set to `only` or `on`, it will add the SSL RabbitMQ check,
    otherwise it will remove it.

    :param nrpe_compat: the NRPE class object
    :type: nrpe.NRPE
    :param unit: NRPE unit
    :type: str
    :param user: username of NRPE user
    :type: str
    :param password: password of NRPE user
    :type: str
    :param vhost: dictionary with vhost and shortname
    :type: Dict[str, str]
    """
    ssl_config = config('ssl') or ''
    if ssl_config.lower() in ['only', 'on']:
        log('Adding rabbitmq SSL check for {}'.format(vhost['vhost']),
            level=DEBUG)
        nrpe_compat.add_check(
            shortname=vhost['shortname'] + "_ssl",
            description='Check RabbitMQ (SSL) {} {}'.format(
                unit, vhost['vhost']),
            check_cmd='{}/check_rabbitmq.py --user {} --password {} '
                      '--vhost {} --ssl --ssl-ca {} --port {}'.format(
                          NAGIOS_PLUGINS, user, password, vhost['vhost'],
                          SSL_CA_FILE, int(config('ssl_port'))))
    else:
        log('Removing rabbitmq SSL check for {}'.format(vhost['vhost']),
            level=DEBUG)
        nrpe_compat.remove_check(
            shortname=vhost['shortname'] + "_ssl",
            description='Remove check RabbitMQ (SSL) {} {}'.format(
                unit, vhost['vhost']),
            check_cmd='{}/check_rabbitmq.py'.format(NAGIOS_PLUGINS))


def is_cron_schedule_valid(cron_schedule):
    """Returns whether or not the stats_cron_schedule can be properly parsed.

    :param cron_schedule: the cron schedule to validate
    :return: True if the cron schedule defined can be parsed by the croniter
             library, False otherwise
    """
    try:
        croniter(cron_schedule).get_next(datetime)
        return True
    except CroniterBadCronError:
        return False


def get_max_stats_file_age():
    """Returns the max stats file age for NRPE checks.

    Max stats file age is determined by a heuristic of 2x the configured
    interval in the stats_cron_schedule config value.

    :return: the maximum age (in seconds) the queues check should consider
             a stats file as aged. If a cron schedule is not defined,
             then return 0.
    :rtype: int
    """
    cron_schedule = config('stats_cron_schedule')
    if not cron_schedule:
        return 0

    try:
        it = croniter(cron_schedule)
        interval = it.get_next(datetime) - it.get_prev(datetime)
        return int(interval.total_seconds() * 2)
    except CroniterBadCronError as err:
        # The config value is being passed straight into croniter and it may
        # not be valid which will cause croniter to raise an error. Catch any
        # of the errors raised.
        log('Specified cron schedule is invalid: %s' % err,
            level=ERROR)
        return 0


def nrpe_update_queues_check(nrpe_compat, rabbit_dir):
    """Add/Remove the RabbitMQ queues check

    The RabbitMQ Queues check should be added if the `queue_thresholds` and
    the `stats_cron_schedule` variables are in the configuration. Otherwise,
    this check should be removed.
    The cron job configured with the `stats_cron_schedule`
    variable is responsible for creating the data files read by this check.

    :param nrpe_compat: the NRPE class object
    :type: nrpe.NRPE
    :param rabbit_dir: path to the RabbitMQ directory
    :type: str
    """
    stats_datafile = os.path.join(
        rabbit_dir, 'data', '{}_queue_stats.dat'.format(get_unit_hostname()))

    if config('queue_thresholds') and config('stats_cron_schedule'):
        cmd = ""
        # If value of queue_thresholds is incorrect we want the hook to fail
        for item in yaml.safe_load(config('queue_thresholds')):
            cmd += ' -c "{}" "{}" {} {}'.format(*item)
        for item in yaml.safe_load(config('exclude_queues')):
            cmd += ' -e "{}" "{}"'.format(*item)
        busiest_queues = config('busiest_queues')
        if busiest_queues is not None and int(busiest_queues) > 0:
            cmd += ' -d "{}"'.format(busiest_queues)

        max_age = get_max_stats_file_age()
        if max_age > 0:
            cmd += ' -m {}'.format(max_age)

        nrpe_compat.add_check(
            shortname=RABBIT_USER + '_queue',
            description='Check RabbitMQ Queues',
            check_cmd='{}/check_rabbitmq_queues.py{} {}'.format(
                NAGIOS_PLUGINS, cmd, stats_datafile))
    else:
        log('Removing rabbitmq Queues check', level=DEBUG)
        nrpe_compat.remove_check(
            shortname=RABBIT_USER + '_queue',
            description='Remove check RabbitMQ Queues',
            check_cmd='{}/check_rabbitmq_queues.py'.format(NAGIOS_PLUGINS))


def nrpe_update_cluster_check(nrpe_compat, user, password):
    """Add/Remove the RabbitMQ cluster check

    If the management_plugin is set to `True`, it will add the cluster RabbitMQ
    check, otherwise it will remove it.

    :param nrpe_compat: the NRPE class object
    :type: nrpe.NRPE
    :param user: username of NRPE user
    :type: str
    :param password: password of NRPE user
    :type: str
    """
    if management_plugin_enabled():
        cmd = '{}/check_rabbitmq_cluster.py --port {} ' \
              '--user {} --password {}'.format(
                  NAGIOS_PLUGINS, get_managment_port(), user, password)
        nrpe_compat.add_check(
            shortname=RABBIT_USER + '_cluster',
            description='Check RabbitMQ Cluster',
            check_cmd=cmd)
    else:
        log('Removing rabbitmq Cluster check', level=DEBUG)
        nrpe_compat.remove_check(
            shortname=RABBIT_USER + '_cluster',
            description='Remove check RabbitMQ Cluster',
            check_cmd='{}/check_rabbitmq_cluster.py'.format(NAGIOS_PLUGINS))


def rabbitmq_version_newer_or_equal(version):
    """Compare the installed RabbitMQ version

    :param version: Version to compare with
    :type: str
    :returns: True if the installed RabbitMQ version is newer or equal.
    :rtype: bool
    """
    rmq_version = get_upstream_version(VERSION_PACKAGE)
    return apt_pkg.version_compare(rmq_version, version) >= 0
