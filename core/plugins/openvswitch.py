from core import plugintools
from core import checks

OPENVSWITCH_SERVICES_EXPRS = [r"ovsdb[a-zA-Z-]*",
                              r"ovs-vswitch[a-zA-Z-]*",
                              r"ovn[a-zA-Z-]*"]
OVS_PKGS_CORE = [r"openvswitch-switch",
                 r"ovn",
                 ]
OVS_PKGS_DEPS = [r"libc-bin",
                 r"openvswitch-switch-dpdk",
                 ]
# Add in clients/deps
for pkg in OVS_PKGS_CORE:
    OVS_PKGS_DEPS.append(r"python3?-{}\S*".format(pkg))


class OpenvSwitchBase(object):
    pass


class OpenvSwitchChecksBase(OpenvSwitchBase, plugintools.PluginPartBase):
    pass


class OpenvSwitchEventChecksBase(OpenvSwitchBase, checks.EventChecksBase):
    pass
