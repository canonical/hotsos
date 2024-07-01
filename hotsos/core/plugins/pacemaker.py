import re
from functools import cached_property

from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase

PACEMAKER_PKGS_CORE = ['pacemaker', r'pacemaker-\S+', 'crmsh', 'corosync']
PACEMAKER_SVC_EXPR = ['pacemaker[a-zA-Z-]*',
                      'corosync']


class PacemakerBase():

    @cached_property
    def crm_status(self):
        return CLIHelper().pacemaker_crm_status

    @cached_property
    def offline_nodes(self):
        crm_status = self.crm_status()
        for line in crm_status:
            regex_match = re.search(r'.*OFFLINE.*\[\s(.*)\s\]',
                                    line)
            if regex_match:
                return regex_match.group(1).split()
        return []

    @cached_property
    def online_nodes(self):
        crm_status = self.crm_status()
        for line in crm_status:
            regex_match = re.search(r'.*Online.*\[\s(.*)\s\]',
                                    line)
            if regex_match:
                return regex_match.group(1).split()
        return []


class PacemakerChecksBase(PacemakerBase, PluginPartBase):
    plugin_name = 'pacemaker'
    plugin_root_index = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt = APTPackageHelper(core_pkgs=PACEMAKER_PKGS_CORE)
        self.systemd = SystemdHelper(service_exprs=PACEMAKER_SVC_EXPR)
        self.pacemaker = PacemakerBase()

    @property
    def plugin_runnable(self):
        return len(self.apt.core) > 0
