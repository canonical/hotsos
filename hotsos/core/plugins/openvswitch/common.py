import abc

from hotsos.core import plugintools
from hotsos.core.host_helpers import (
    APTPackageHelper,
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
OVS_PKGS_CORE = ['openvswitch-switch',
                 'ovn',
                 ]
OVS_PKGS_DEPS = ['libc-bin',
                 'openvswitch',
                 'ovsdbapp',
                 'openssl',
                 'openvswitch-switch-dpdk',
                 ]
PY_CLIENT_PREFIX = r"python3?-{}\S*"


class OpenvSwitchGlobalSearchBase(GlobalSearcherAutoRegisterBase):
    """ Base class for global searcher registration for OpenvSwitch. """
    plugin_name = "openvswitch"

    @classmethod
    @abc.abstractmethod
    def paths(cls):
        """ Returns a list of one or more paths to search. """


class OpenvSwitchChecks(plugintools.PluginPartBase):
    """ OpenvSwitch checks. """
    plugin_name = "openvswitch"
    plugin_root_index = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p_core = OVS_PKGS_CORE + [PY_CLIENT_PREFIX.format(p)
                                  for p in OVS_PKGS_CORE]
        p_deps = OVS_PKGS_DEPS + [PY_CLIENT_PREFIX.format(p)
                                  for p in OVS_PKGS_DEPS]
        self.apt = APTPackageHelper(core_pkgs=p_core, other_pkgs=p_deps)
        self.pebble = PebbleHelper(service_exprs=OVS_SERVICES_EXPRS)
        self.systemd = SystemdHelper(service_exprs=OVS_SERVICES_EXPRS)

    @property
    def plugin_runnable(self):
        # require at least one core package to be installed to run this plugin.
        return len(self.apt.core) > 0


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
