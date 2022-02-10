# Copyright 2012-2021 Canonical Limited.
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

"""Compatibility with the nrpe-external-master charm"""
#
# Authors:
#  Matthew Wedgwood <matthew.wedgwood@canonical.com>

import glob
import grp
import os
import pwd
import re
import shlex
import shutil
import subprocess
import yaml

from charmhelpers.core.hookenv import (
    config,
    hook_name,
    local_unit,
    log,
    relation_get,
    relation_ids,
    relation_set,
    relations_of_type,
)

from charmhelpers.core.host import service
from charmhelpers.core import host

# This module adds compatibility with the nrpe-external-master and plain nrpe
# subordinate charms. To use it in your charm:
#
# 1. Update metadata.yaml
#
#   provides:
#     (...)
#     nrpe-external-master:
#       interface: nrpe-external-master
#       scope: container
#
#   and/or
#
#   provides:
#     (...)
#     local-monitors:
#       interface: local-monitors
#       scope: container

#
# 2. Add the following to config.yaml
#
#    nagios_context:
#      default: "juju"
#      type: string
#      description: |
#        Used by the nrpe subordinate charms.
#        A string that will be prepended to instance name to set the host name
#        in nagios. So for instance the hostname would be something like:
#            juju-myservice-0
#        If you're running multiple environments with the same services in them
#        this allows you to differentiate between them.
#    nagios_servicegroups:
#      default: ""
#      type: string
#      description: |
#        A comma-separated list of nagios servicegroups.
#        If left empty, the nagios_context will be used as the servicegroup
#
# 3. Add custom checks (Nagios plugins) to files/nrpe-external-master
#
# 4. Update your hooks.py with something like this:
#
#    from charmsupport.nrpe import NRPE
#    (...)
#    def update_nrpe_config():
#        nrpe_compat = NRPE()
#        nrpe_compat.add_check(
#            shortname = "myservice",
#            description = "Check MyService",
#            check_cmd = "check_http -w 2 -c 10 http://localhost"
#            )
#        nrpe_compat.add_check(
#            "myservice_other",
#            "Check for widget failures",
#            check_cmd = "/srv/myapp/scripts/widget_check"
#            )
#        nrpe_compat.write()
#
#    def config_changed():
#        (...)
#        update_nrpe_config()
#
#    def nrpe_external_master_relation_changed():
#        update_nrpe_config()
#
#    def local_monitors_relation_changed():
#        update_nrpe_config()
#
# 4.a If your charm is a subordinate charm set primary=False
#
#    from charmsupport.nrpe import NRPE
#    (...)
#    def update_nrpe_config():
#        nrpe_compat = NRPE(primary=False)
#
# 5. ln -s hooks.py nrpe-external-master-relation-changed
#    ln -s hooks.py local-monitors-relation-changed


class CheckException(Exception):
    pass


class Check(object):
    shortname_re = '[A-Za-z0-9-_.@]+$'
    service_template = ("""
#---------------------------------------------------
# This file is Juju managed
#---------------------------------------------------
define service {{
    use                             active-service
    host_name                       {nagios_hostname}
    service_description             {nagios_hostname}[{shortname}] """
                        """{description}
    check_command                   check_nrpe!{command}
    servicegroups                   {nagios_servicegroup}
{service_config_overrides}
}}
""")

    def __init__(self, shortname, description, check_cmd, max_check_attempts=None):
        super(Check, self).__init__()
        # XXX: could be better to calculate this from the service name
        if not re.match(self.shortname_re, shortname):
            raise CheckException("shortname must match {}".format(
                Check.shortname_re))
        self.shortname = shortname
        self.command = "check_{}".format(shortname)
        # Note: a set of invalid characters is defined by the
        # Nagios server config
        # The default is: illegal_object_name_chars=`~!$%^&*"|'<>?,()=
        self.description = description
        self.check_cmd = self._locate_cmd(check_cmd)
        self.max_check_attempts = max_check_attempts

    def _get_check_filename(self):
        return os.path.join(NRPE.nrpe_confdir, '{}.cfg'.format(self.command))

    def _get_service_filename(self, hostname):
        return os.path.join(NRPE.nagios_exportdir,
                            'service__{}_{}.cfg'.format(hostname, self.command))

    def _locate_cmd(self, check_cmd):
        search_path = (
            '/usr/lib/nagios/plugins',
            '/usr/local/lib/nagios/plugins',
        )
        parts = shlex.split(check_cmd)
        for path in search_path:
            if os.path.exists(os.path.join(path, parts[0])):
                command = os.path.join(path, parts[0])
                if len(parts) > 1:
                    command += " " + " ".join(parts[1:])
                return command
        log('Check command not found: {}'.format(parts[0]))
        return ''

    def _remove_service_files(self):
        if not os.path.exists(NRPE.nagios_exportdir):
            return
        for f in os.listdir(NRPE.nagios_exportdir):
            if f.endswith('_{}.cfg'.format(self.command)):
                os.remove(os.path.join(NRPE.nagios_exportdir, f))

    def remove(self, hostname):
        nrpe_check_file = self._get_check_filename()
        if os.path.exists(nrpe_check_file):
            os.remove(nrpe_check_file)
        self._remove_service_files()

    def write(self, nagios_context, hostname, nagios_servicegroups):
        nrpe_check_file = self._get_check_filename()
        with open(nrpe_check_file, 'w') as nrpe_check_config:
            nrpe_check_config.write("# check {}\n".format(self.shortname))
            if nagios_servicegroups:
                nrpe_check_config.write(
                    "# The following header was added automatically by juju\n")
                nrpe_check_config.write(
                    "# Modifying it will affect nagios monitoring and alerting\n")
                nrpe_check_config.write(
                    "# servicegroups: {}\n".format(nagios_servicegroups))
            nrpe_check_config.write("command[{}]={}\n".format(
                self.command, self.check_cmd))

        if not os.path.exists(NRPE.nagios_exportdir):
            log('Not writing service config as {} is not accessible'.format(
                NRPE.nagios_exportdir))
        else:
            self.write_service_config(nagios_context, hostname,
                                      nagios_servicegroups)

    def write_service_config(self, nagios_context, hostname,
                             nagios_servicegroups):
        self._remove_service_files()

        if self.max_check_attempts:
            service_config_overrides = '    max_check_attempts              {}'.format(
                self.max_check_attempts
            )  # Note indentation is here rather than in the template to avoid trailing spaces
        else:
            service_config_overrides = ''  # empty string to avoid printing 'None'
        templ_vars = {
            'nagios_hostname': hostname,
            'nagios_servicegroup': nagios_servicegroups,
            'description': self.description,
            'shortname': self.shortname,
            'command': self.command,
            'service_config_overrides': service_config_overrides,
        }
        nrpe_service_text = Check.service_template.format(**templ_vars)
        nrpe_service_file = self._get_service_filename(hostname)
        with open(nrpe_service_file, 'w') as nrpe_service_config:
            nrpe_service_config.write(str(nrpe_service_text))

    def run(self):
        subprocess.call(self.check_cmd)


class NRPE(object):
    nagios_logdir = '/var/log/nagios'
    nagios_exportdir = '/var/lib/nagios/export'
    nrpe_confdir = '/etc/nagios/nrpe.d'
    homedir = '/var/lib/nagios'  # home dir provided by nagios-nrpe-server

    def __init__(self, hostname=None, primary=True):
        super(NRPE, self).__init__()
        self.config = config()
        self.primary = primary
        self.nagios_context = self.config['nagios_context']
        if 'nagios_servicegroups' in self.config and self.config['nagios_servicegroups']:
            self.nagios_servicegroups = self.config['nagios_servicegroups']
        else:
            self.nagios_servicegroups = self.nagios_context
        self.unit_name = local_unit().replace('/', '-')
        if hostname:
            self.hostname = hostname
        else:
            nagios_hostname = get_nagios_hostname()
            if nagios_hostname:
                self.hostname = nagios_hostname
            else:
                self.hostname = "{}-{}".format(self.nagios_context, self.unit_name)
        self.checks = []
        # Iff in an nrpe-external-master relation hook, set primary status
        relation = relation_ids('nrpe-external-master')
        if relation:
            log("Setting charm primary status {}".format(primary))
            for rid in relation:
                relation_set(relation_id=rid, relation_settings={'primary': self.primary})
        self.remove_check_queue = set()

    @classmethod
    def does_nrpe_conf_dir_exist(cls):
        """Return True if th nrpe_confdif directory exists."""
        return os.path.isdir(cls.nrpe_confdir)

    def add_check(self, *args, **kwargs):
        shortname = None
        if kwargs.get('shortname') is None:
            if len(args) > 0:
                shortname = args[0]
        else:
            shortname = kwargs['shortname']

        self.checks.append(Check(*args, **kwargs))
        try:
            self.remove_check_queue.remove(shortname)
        except KeyError:
            pass

    def remove_check(self, *args, **kwargs):
        if kwargs.get('shortname') is None:
            raise ValueError('shortname of check must be specified')

        # Use sensible defaults if they're not specified - these are not
        # actually used during removal, but they're required for constructing
        # the Check object; check_disk is chosen because it's part of the
        # nagios-plugins-basic package.
        if kwargs.get('check_cmd') is None:
            kwargs['check_cmd'] = 'check_disk'
        if kwargs.get('description') is None:
            kwargs['description'] = ''

        check = Check(*args, **kwargs)
        check.remove(self.hostname)
        self.remove_check_queue.add(kwargs['shortname'])

    def write(self):
        try:
            nagios_uid = pwd.getpwnam('nagios').pw_uid
            nagios_gid = grp.getgrnam('nagios').gr_gid
        except Exception:
            log("Nagios user not set up, nrpe checks not updated")
            return

        if not os.path.exists(NRPE.nagios_logdir):
            os.mkdir(NRPE.nagios_logdir)
            os.chown(NRPE.nagios_logdir, nagios_uid, nagios_gid)

        nrpe_monitors = {}
        monitors = {"monitors": {"remote": {"nrpe": nrpe_monitors}}}

        # check that the charm can write to the conf dir.  If not, then nagios
        # probably isn't installed, and we can defer.
        if not self.does_nrpe_conf_dir_exist():
            return

        for nrpecheck in self.checks:
            nrpecheck.write(self.nagios_context, self.hostname,
                            self.nagios_servicegroups)
            nrpe_monitors[nrpecheck.shortname] = {
                "command": nrpecheck.command,
            }
            # If we were passed max_check_attempts, add that to the relation data
            if nrpecheck.max_check_attempts is not None:
                nrpe_monitors[nrpecheck.shortname]['max_check_attempts'] = nrpecheck.max_check_attempts

        # update-status hooks are configured to firing every 5 minutes by
        # default. When nagios-nrpe-server is restarted, the nagios server
        # reports checks failing causing unnecessary alerts. Let's not restart
        # on update-status hooks.
        if not hook_name() == 'update-status':
            service('restart', 'nagios-nrpe-server')

        monitor_ids = relation_ids("local-monitors") + \
            relation_ids("nrpe-external-master")
        for rid in monitor_ids:
            reldata = relation_get(unit=local_unit(), rid=rid)
            if 'monitors' in reldata:
                # update the existing set of monitors with the new data
                old_monitors = yaml.safe_load(reldata['monitors'])
                old_nrpe_monitors = old_monitors['monitors']['remote']['nrpe']
                # remove keys that are in the remove_check_queue
                old_nrpe_monitors = {k: v for k, v in old_nrpe_monitors.items()
                                     if k not in self.remove_check_queue}
                # update/add nrpe_monitors
                old_nrpe_monitors.update(nrpe_monitors)
                old_monitors['monitors']['remote']['nrpe'] = old_nrpe_monitors
                # write back to the relation
                relation_set(relation_id=rid, monitors=yaml.dump(old_monitors))
            else:
                # write a brand new set of monitors, as no existing ones.
                relation_set(relation_id=rid, monitors=yaml.dump(monitors))

        self.remove_check_queue.clear()


def get_nagios_hostcontext(relation_name='nrpe-external-master'):
    """
    Query relation with nrpe subordinate, return the nagios_host_context

    :param str relation_name: Name of relation nrpe sub joined to
    """
    for rel in relations_of_type(relation_name):
        if 'nagios_host_context' in rel:
            return rel['nagios_host_context']


def get_nagios_hostname(relation_name='nrpe-external-master'):
    """
    Query relation with nrpe subordinate, return the nagios_hostname

    :param str relation_name: Name of relation nrpe sub joined to
    """
    for rel in relations_of_type(relation_name):
        if 'nagios_hostname' in rel:
            return rel['nagios_hostname']


def get_nagios_unit_name(relation_name='nrpe-external-master'):
    """
    Return the nagios unit name prepended with host_context if needed

    :param str relation_name: Name of relation nrpe sub joined to
    """
    host_context = get_nagios_hostcontext(relation_name)
    if host_context:
        unit = "%s:%s" % (host_context, local_unit())
    else:
        unit = local_unit()
    return unit


def add_init_service_checks(nrpe, services, unit_name, immediate_check=True):
    """
    Add checks for each service in list

    :param NRPE nrpe: NRPE object to add check to
    :param list services: List of services to check
    :param str unit_name: Unit name to use in check description
    :param bool immediate_check: For sysv init, run the service check immediately
    """
    for svc in services:
        # Don't add a check for these services from neutron-gateway
        if svc in ['ext-port', 'os-charm-phy-nic-mtu']:
            next

        upstart_init = '/etc/init/%s.conf' % svc
        sysv_init = '/etc/init.d/%s' % svc

        if host.init_is_systemd(service_name=svc):
            nrpe.add_check(
                shortname=svc,
                description='process check {%s}' % unit_name,
                check_cmd='check_systemd.py %s' % svc
            )
        elif os.path.exists(upstart_init):
            nrpe.add_check(
                shortname=svc,
                description='process check {%s}' % unit_name,
                check_cmd='check_upstart_job %s' % svc
            )
        elif os.path.exists(sysv_init):
            cronpath = '/etc/cron.d/nagios-service-check-%s' % svc
            checkpath = '%s/service-check-%s.txt' % (nrpe.homedir, svc)
            croncmd = (
                '/usr/local/lib/nagios/plugins/check_exit_status.pl '
                '-e -s /etc/init.d/%s status' % svc
            )
            cron_file = '*/5 * * * * root %s > %s\n' % (croncmd, checkpath)
            f = open(cronpath, 'w')
            f.write(cron_file)
            f.close()
            nrpe.add_check(
                shortname=svc,
                description='service check {%s}' % unit_name,
                check_cmd='check_status_file.py -f %s' % checkpath,
            )
            # if /var/lib/nagios doesn't exist open(checkpath, 'w') will fail
            # (LP: #1670223).
            if immediate_check and os.path.isdir(nrpe.homedir):
                f = open(checkpath, 'w')
                subprocess.call(
                    croncmd.split(),
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
                f.close()
                os.chmod(checkpath, 0o644)


def copy_nrpe_checks(nrpe_files_dir=None):
    """
    Copy the nrpe checks into place

    """
    NAGIOS_PLUGINS = '/usr/local/lib/nagios/plugins'
    if nrpe_files_dir is None:
        # determine if "charmhelpers" is in CHARMDIR or CHARMDIR/hooks
        for segment in ['.', 'hooks']:
            nrpe_files_dir = os.path.abspath(os.path.join(
                os.getenv('CHARM_DIR'),
                segment,
                'charmhelpers',
                'contrib',
                'openstack',
                'files'))
            if os.path.isdir(nrpe_files_dir):
                break
        else:
            raise RuntimeError("Couldn't find charmhelpers directory")
    if not os.path.exists(NAGIOS_PLUGINS):
        os.makedirs(NAGIOS_PLUGINS)
    for fname in glob.glob(os.path.join(nrpe_files_dir, "check_*")):
        if os.path.isfile(fname):
            shutil.copy2(fname,
                         os.path.join(NAGIOS_PLUGINS, os.path.basename(fname)))


def add_haproxy_checks(nrpe, unit_name):
    """
    Add checks for each service in list

    :param NRPE nrpe: NRPE object to add check to
    :param str unit_name: Unit name to use in check description
    """
    nrpe.add_check(
        shortname='haproxy_servers',
        description='Check HAProxy {%s}' % unit_name,
        check_cmd='check_haproxy.sh')
    nrpe.add_check(
        shortname='haproxy_queue',
        description='Check HAProxy queue depth {%s}' % unit_name,
        check_cmd='check_haproxy_queue_depth.sh')


def remove_deprecated_check(nrpe, deprecated_services):
    """
    Remove checks for deprecated services in list

    :param nrpe: NRPE object to remove check from
    :type nrpe: NRPE
    :param deprecated_services: List of deprecated services that are removed
    :type deprecated_services: list
    """
    for dep_svc in deprecated_services:
        log('Deprecated service: {}'.format(dep_svc))
        nrpe.remove_check(shortname=dep_svc)
