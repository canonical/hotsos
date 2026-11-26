import glob
import os
from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    CLIHelper,
    InstallInfoBase,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core.plugins.juju.resources import JujuBase
from hotsos.core import plugintools

SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
JUJU_SVC_EXPRS = [rf'mongod{SVC_VALID_SUFFIX}',
                  rf'jujud{SVC_VALID_SUFFIX}',
                  # catch juju-db but filter out processes with juju-db in
                  # their args list.
                  rf'(?:^|[^\s])juju-db{SVC_VALID_SUFFIX}']
# Namespaces created by Kubernetes for its own components.
K8S_SYSTEM_NAMESPACES = ['kube-node-lease', 'kube-public', 'kube-system']


@dataclass
class JujuInstallInfo(InstallInfoBase):
    """ Juju installation information. """
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(service_exprs=JUJU_SVC_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=JUJU_SVC_EXPRS))


class JujuChecks(plugintools.PluginPartBase, JujuBase):
    """ Juju checks. """
    plugin_name = 'juju'
    plugin_root_index = 12

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        JujuInstallInfo().mixin(self)

    @cached_property
    def systemd_processes(self):
        """
        Return a list of running processes related to the Juju service. This
        is needed for Juju scenarios.
        """
        return self.systemd.processes

    @property
    def version(self):
        if self.machine:
            return self.machine.version

        return "unknown"

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        if os.path.exists(cls.get_juju_lib_path()):
            return True

        # Kubernetes units have no local Juju state. Juju runs the agent of
        # each unit in a container named "charm" in the unit pod so the
        # presence of any such container is used to determine that Juju is in
        # use.
        podlogs = os.path.join(HotSOSConfig.data_root,
                               'sos_commands/kubernetes/cluster-info/*/'
                               'podlogs/*/*_logs_*_-c_charm')
        if glob.glob(podlogs):
            return True

        return cls._has_charm_containers()

    @staticmethod
    def _has_charm_containers():
        """ Return True if any pod has a Juju charm container. """
        cli = CLIHelper()
        out = cli.kubectl_get(namespace='none', opt='namespaces', subopts='')
        if not out or 'items' not in out:
            return False

        for item in out['items']:
            namespace = item['metadata']['name']
            if namespace in K8S_SYSTEM_NAMESPACES:
                continue

            pods = cli.kubectl_get(namespace=namespace, opt='pods',
                                   subopts='')
            if not pods or 'items' not in pods:
                continue

            for pod in pods['items']:
                containers = pod['spec']['containers']
                if any(c['name'] == 'charm' for c in containers):
                    return True

        return False
