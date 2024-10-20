from dataclasses import dataclass, field
import re
from functools import cached_property

from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelper,
    InstallInfoBase,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase

PACEMAKER_PKGS_CORE = ['pacemaker', r'pacemaker-\S+', 'crmsh', 'corosync']
PACEMAKER_SVC_EXPR = ['pacemaker[a-zA-Z-]*',
                      'corosync']


@dataclass
class PacemakerInstallInfo(InstallInfoBase):
    """ Pacemaker installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(
                                                core_pkgs=PACEMAKER_PKGS_CORE))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(
                                            service_exprs=PACEMAKER_SVC_EXPR))


class PacemakerBase():
    """ Base class for pacemaker checks. """
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


class PacemakerChecks(PacemakerBase, PluginPartBase):
    """ Pacemaker checks. """
    plugin_name = 'pacemaker'
    plugin_root_index = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        PacemakerInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        return len(PacemakerInstallInfo().apt.core) > 0
