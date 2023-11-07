from hotsos.core import plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    APTPackageHelper,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core.ycheck.events import EventCallbackBase, EventHandlerBase
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


class OpenvSwitchChecksBase(plugintools.PluginPartBase):
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

    def categorise_events(self, *args, **kwargs):
        if 'include_time' not in kwargs:
            include_time = HotSOSConfig.event_tally_granularity == 'time'
            kwargs['include_time'] = include_time

        return super().categorise_events(*args, **kwargs)


class OpenvSwitchEventHandlerBase(OpenvSwitchChecksBase, EventHandlerBase):

    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.load_and_run()
        if ret:
            return sorted_dict(ret)
