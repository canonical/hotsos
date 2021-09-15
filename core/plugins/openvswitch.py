from core import plugintools
from core import checks

OVS_SERVICES_EXPRS = [r"ovsdb[a-zA-Z-]*",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=OVS_PKGS_CORE,
                                                     other_pkgs=OVS_PKGS_DEPS)
        svc_exprs = OVS_SERVICES_EXPRS
        self.svc_check = checks.ServiceChecksBase(service_exprs=svc_exprs)

    @property
    def plugin_runnable(self):
        # require at least one core package to be installed to run this plugin.
        return len(self.apt_check.core) > 0


class OpenvSwitchEventChecksBase(OpenvSwitchBase, checks.EventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=OVS_PKGS_CORE,
                                                     other_pkgs=OVS_PKGS_DEPS)

    @property
    def plugin_runnable(self):
        # require at least one core package to be installed to run this plugin.
        return len(self.apt_check.core) > 0
