from core import plugintools
from core import checks
from core.cli_helpers import CLIHelper

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cli = CLIHelper()

    @property
    def bridges(self):
        bridges = self.cli.ovs_vsctl_list_br()
        return [br.strip() for br in bridges]

    @property
    def offload_enabled(self):
        other_config = self.cli.ovs_vsctl_get_Open_vSwitch_other_config()
        if not other_config:
            return False

        if 'hw-offload="true"' in other_config:
            return True

        return False


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


class OpenvSwitchEventChecksBase(OpenvSwitchChecksBase,
                                 checks.EventChecksBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)
