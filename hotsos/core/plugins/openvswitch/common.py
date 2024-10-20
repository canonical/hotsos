import abc
from dataclasses import dataclass, field

from hotsos.core import plugintools
from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core.ycheck.events import EventCallbackBase, EventHandlerBase
from hotsos.core.ycheck.common import GlobalSearcherAutoRegisterBase
from hotsos.core.utils import sorted_dict

OVS_SERVICES_EXPRS = [r'ovsdb[a-zA-Z-]*',
                      r'ovs-vswitch[a-zA-Z-]*',
                      r'ovn[a-zA-Z-]*',
                      'openvswitch-switch',
                      ]
PY_CLIENT_PREFIX = r"python3?-{}\S*"
_OVS_PKGS_CORE = ['openvswitch-switch',
                  'ovn',
                  ]
OVS_PKGS_CORE = _OVS_PKGS_CORE + \
                [PY_CLIENT_PREFIX.format(p) for p in _OVS_PKGS_CORE]
_OVS_PKGS_DEPS = ['libc-bin',
                  'openvswitch',
                  'ovsdbapp',
                  'openssl',
                  'openvswitch-switch-dpdk',
                  ]
OVS_PKGS_DEPS = _OVS_PKGS_DEPS + \
                [PY_CLIENT_PREFIX.format(p) for p in _OVS_PKGS_DEPS]


class OpenvSwitchGlobalSearchBase(GlobalSearcherAutoRegisterBase):
    """ Base class for global searcher registration for OpenvSwitch. """
    plugin_name = "openvswitch"

    @classmethod
    @abc.abstractmethod
    def paths(cls):
        """ Returns a list of one or more paths to search. """


@dataclass
class OpenvSwitchInstallInfo(InstallInfoBase):
    """ OpenvSwitch installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=OVS_PKGS_CORE,
                                                   other_pkgs=OVS_PKGS_DEPS))
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(
                                            service_exprs=OVS_SERVICES_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(
                                            service_exprs=OVS_SERVICES_EXPRS))


class OpenvSwitchChecks(plugintools.PluginPartBase):
    """ OpenvSwitch checks. """
    plugin_name = "openvswitch"
    plugin_root_index = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        OpenvSwitchInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        # require at least one core package to be installed to run this plugin.
        return len(OpenvSwitchInstallInfo().apt.core) > 0


class OpenvSwitchEventCallbackBase(EventCallbackBase):
    """ Base class for OpenvSwitch events callbacks. """
    @classmethod
    def global_event_tally_time_granularity_override(cls):
        return True

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class OpenvSwitchEventHandlerBase(OpenvSwitchChecks, EventHandlerBase):
    """ Base class for OpenvSwitch event handlers. """
    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.run()
        if ret:
            return sorted_dict(ret)

        return None
