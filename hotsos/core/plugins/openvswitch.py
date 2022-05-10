import re

from hotsos.core import plugintools
from hotsos.core import host_helpers
from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core.utils import sorted_dict


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


class OVSDPLookups(object):

    def __init__(self):
        cli = host_helpers.CLIHelper()
        out = cli.ovs_appctl_dpctl_show(datapath='system@ovs-system')
        cexpr = re.compile(r'\s*lookups: hit:(\S+) missed:(\S+) lost:(\S+)')
        self.fields = {'hit': 0, 'missed': 0, 'lost': 0}
        for line in out:
            ret = re.match(cexpr, line)
            if ret:
                self.fields['hit'] = int(ret.group(1))
                self.fields['missed'] = int(ret.group(2))
                self.fields['lost'] = int(ret.group(3))

    def __getattr__(self, key):
        if key in self.fields:
            return self.fields[key]


class OVSBridge(object):

    def __init__(self, name, nethelper):
        self.name = name
        self.cli = host_helpers.CLIHelper()
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
        self.cli = host_helpers.CLIHelper()
        self.net_helper = host_helpers.HostNetworkingHelper()

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
        self.apt_check = host_helpers.APTPackageChecksBase(
                                                      core_pkgs=OVS_PKGS_CORE,
                                                      other_pkgs=OVS_PKGS_DEPS)
        svc_exprs = OVS_SERVICES_EXPRS
        self.svc_check = host_helpers.ServiceChecksBase(
                                                       service_exprs=svc_exprs)

    @property
    def apt_packages_all(self):
        return self.apt_check.all

    @property
    def plugin_runnable(self):
        # require at least one core package to be installed to run this plugin.
        return len(self.apt_check.core) > 0


class OpenvSwitchEventChecksBase(OpenvSwitchChecksBase, YEventCheckerBase):

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

        @param results: a list of SearchResult objects containing up to two
                        groups; a date and a resource. If the second group
                        (resource) is not available, all results will be
                        grouped by date.
        @param key_by_date: by default the results are collected by datetime
                            i.e. for each timestamp show how many of each
                            resource occured.
        """
        force_by_date = False
        stats = {}
        for r in results:
            if key_by_date:
                key = r.get(1)
                value = r.get(2)
            else:
                key = r.get(2)
                value = r.get(1)

            if value is None or force_by_date:
                force_by_date = True
                value = "sentinel"

            if key not in stats:
                stats[key] = {}

            if value not in stats[key]:
                stats[key][value] = 1
            else:
                stats[key][value] += 1

            # sort each keyset
            if not key_by_date:
                stats[key] = self._stats_sort(stats[key])

        combined = {}
        if force_by_date:
            for k, v in stats.items():
                combined[k] = 0
                for count in v.values():
                    combined[k] += count

            stats = combined

        if stats:
            # only if sorted per key
            if key_by_date:
                stats = self._stats_sort(stats)

            return stats

    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.run_checks()
        if ret:
            return sorted_dict(ret)
