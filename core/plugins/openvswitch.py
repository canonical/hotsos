import re

from core import plugintools
from core import checks
from core.cli_helpers import CLIHelper
from core.host_helpers import HostNetworkingHelper


OVS_SERVICES_EXPRS = [r"ovsdb[a-zA-Z-]*",
                      r"ovs-vswitch[a-zA-Z-]*",
                      r"ovn[a-zA-Z-]*",
                      "openvswitch-switch"]
OVS_PKGS_CORE = [r"openvswitch-switch",
                 r"ovn",
                 ]
OVS_PKGS_DEPS = [r"libc-bin",
                 r"openvswitch-switch-dpdk",
                 ]
# Add in clients/deps
for pkg in OVS_PKGS_CORE:
    OVS_PKGS_DEPS.append(r"python3?-{}\S*".format(pkg))


class OVSBridge(object):

    def __init__(self, name, nethelper):
        self.name = name
        self.cli = CLIHelper()
        self.nethelper = nethelper

    @property
    def ports(self):
        ports = []
        for line in self.cli.ovs_ofctl_show(bridge=self.name):
            ret = re.compile(r'^\s+\d+\((\S+)\):\s+').match(line)
            if ret:
                name = ret.group(1)
                port = self.nethelper.get_interface_with_name(name)
                if not port:
                    port = name

                ports.append(port)

        return ports


class OpenvSwitchBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cli = CLIHelper()
        self.net_helper = HostNetworkingHelper()

    @property
    def bridges(self):
        bridges = self.cli.ovs_vsctl_list_br()
        return [OVSBridge(br.strip(), self.net_helper) for br in bridges]

    def _record_to_dict(self, record):
        record_dict = {}
        if record:
            for field in re.compile(r'(\S+,)').findall(record):
                for char in [',', '}', '{']:
                    field = field.strip(char)

                key, _, val = field.partition('=')
                record_dict[key] = val.strip('"')

        return record_dict

    @property
    def external_ids(self):
        config = self.cli.ovs_vsctl_get_Open_vSwitch(record='external_ids')
        if not config:
            for line in self.cli.ovs_vsctl_list_Open_vSwitch():
                if line.startswith('external_ids '):
                    config = line.partition(':')[2].strip()
                    break

        return self._record_to_dict(config)

    @property
    def other_config(self):
        config = self.cli.ovs_vsctl_get_Open_vSwitch(record='other_config')
        return self._record_to_dict(config)

    @property
    def offload_enabled(self):
        config = self.other_config
        if not config:
            return False

        if config.get('hw-offload') == "true":
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

    def _stats_sort(self, stats):
        stats_sorted = {}
        for k, v in sorted(stats.items(),
                           key=lambda x: x[0]):
            stats_sorted[k] = v

        return stats_sorted

    def get_results_stats(self, results, key_by_date=True):
        """
        Collect information about how often a resource occurs. A resource can
        be anything e.g. an interface or a loglevel string.

        @param results: a list of SearchResult objects containing two groups; a
                        date and a resource.
        @param key_by_date: by default the results are collected by datetime
                            i.e. for each timestamp show how many of each
                            resource occured.
        """
        stats = {}
        for r in results:
            if key_by_date:
                key = r.get(1)
                value = r.get(2)
            else:
                key = r.get(2)
                value = r.get(1)

            if key not in stats:
                stats[key] = {}

            if value not in stats[key]:
                stats[key][value] = 1
            else:
                stats[key][value] += 1

            # sort each keyset
            if not key_by_date:
                stats[key] = self._stats_sort(stats[key])

        if stats:
            # only if sorted per key
            if key_by_date:
                stats = self._stats_sort(stats)

            return stats

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)
