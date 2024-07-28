import re

from hotsos.core.host_helpers import CLIHelper, HostNetworkingHelper
from hotsos.core.plugins.openstack.common import OpenStackChecks
from hotsos.core.plugins.openstack.neutron import (
    IP_HEADER_BYTES,
    GRE_HEADER_BYTES,
    VXLAN_HEADER_BYTES,
)
from hotsos.core.plugins.openvswitch import OpenvSwitchBase
from hotsos.core.issues import (
    IssuesManager,
    OpenstackWarning,
)
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class OpenstackNetworkChecks(OpenStackChecks):
    """ Implements OpenStack network checks. """
    summary_part_index = 4

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cli = CLIHelper()

    @property
    def summary_subkey(self):
        return 'network'

    @staticmethod
    def _get_port_stat_outliers(counters):
        """ For a given port's packet counters, identify outliers i.e. > 1%
        and create a new dict with count and percent values.
        """
        stats = {}
        for rxtx in counters:
            total = sum(counters[rxtx].values())
            for key, value in counters[rxtx].items():
                if key == "packets":
                    continue

                if value:
                    pcent = int(100 / float(total) * float(value))
                    if pcent <= 1:
                        continue

                    if rxtx not in stats:
                        stats[rxtx] = {}

                    stats[rxtx][key] = f"{int(value)} ({pcent}%)"

        return stats

    def get_config_info(self):
        config_info = {}
        for project in ['nova', 'neutron', 'octavia']:
            _project = getattr(self, project)
            if _project and _project.bind_interfaces:
                for name, port in _project.bind_interfaces.items():
                    if project not in config_info:
                        config_info[project] = {}

                    config_info[project][name] = port.to_dict()

        return config_info

    def get_phy_port_health_info(self):
        """ Identify ports used by Openstack services, include them in output
        for informational purposes along with their health (dropped packets
        etc) for any outliers detected.
        """
        port_health_info = {}
        for project in ['nova', 'neutron', 'octavia']:
            _project = getattr(self, project)
            if _project and _project.bind_interfaces:
                for port in _project.bind_interfaces.values():
                    if port.stats:
                        stats = self._get_port_stat_outliers(port.stats)
                        if not stats:
                            continue

                        port_health_info[port.name] = stats

        return port_health_info

    @summary_entry('config', get_min_available_entry_index() + 5)
    def summary_config(self):
        config_info = self.get_config_info()
        if config_info:
            return config_info

        return None

    @summary_entry('phy-port-health', get_min_available_entry_index() + 6)
    def summary_phy_port_health(self):
        port_health_info = self.get_phy_port_health_info()
        if port_health_info:
            return port_health_info

        return None

    @summary_entry('namespaces', get_min_available_entry_index() + 7)
    def summary_namespaces(self):
        """Populate namespace information dict."""
        ns_info = {}
        for line in self.cli.ip_netns():
            ret = re.compile(r"^([a-z0-9]+)-([0-9a-z\-]+)\s+.+").match(line)
            if ret:
                if ret[1] in ns_info:
                    ns_info[ret[1]] += 1
                else:
                    ns_info[ret[1]] = 1

        if ns_info:
            return ns_info

        return None

    def _get_router_iface_mtus(self):
        """
        Get the mtu of each qr and qg port in every qrouter or snat namespace.

        @return: dictionary of port prefixes and list of mtus associated with
                 those prefixes.
        """
        router_mtus = {}
        for ns in self.cli.ip_netns():
            # strip index
            ns = ns.partition(" ")[0]
            for nsprefix in ['qrouter', 'snat']:
                if not ns.startswith(nsprefix):
                    continue

                for port in HostNetworkingHelper().get_ns_interfaces(ns):
                    for pprefix in ['qr', 'sg']:
                        if not port.name.startswith(pprefix):
                            continue

                        if pprefix not in router_mtus:
                            router_mtus[pprefix] = set()

                        router_mtus[pprefix].add(port.mtu)

        return {prefix: list(mtus) for prefix, mtus in router_mtus.items()}

    @summary_entry('router-port-mtus', get_min_available_entry_index() + 8)
    def summary_router_port_mtus(self):
        """ Provide a summary of ml2-ovs router port mtus. """
        project = getattr(self, 'neutron')
        if not (project and project.bind_interfaces):
            return None

        phy_mtus = set()
        for port in project.bind_interfaces.values():
            phy_mtus.add(port.mtu)

        tunnels = OpenvSwitchBase().tunnels
        # ip header
        overhead = IP_HEADER_BYTES
        if 'vxlan' in tunnels:
            overhead += VXLAN_HEADER_BYTES
        else:
            # gre
            overhead += GRE_HEADER_BYTES

        router_mtus = self._get_router_iface_mtus()
        all_router_mtus = set()
        for mtus in router_mtus.values():
            all_router_mtus.update(mtus)

        if phy_mtus and all_router_mtus:
            smallest_allowed = min(phy_mtus) - overhead
            if max(all_router_mtus) > smallest_allowed:
                msg = ("This Neutron L3 agent host has one or more router "
                       f"ports with mtu={max(all_router_mtus)} which is "
                       "greater or equal to the smallest allowed "
                       f"({smallest_allowed}) on the physical network. "
                       "This will result in dropped packets or "
                       "unexpected fragmentation in overlay networks.")
                IssuesManager().add(OpenstackWarning(msg))

        return router_mtus

    @summary_entry('vm-port-health', get_min_available_entry_index() + 9)
    def summary_vm_port_health(self):
        """ For each instance get its ports and check port health, reporting on
        any outliers. """
        if not self.nova.instances:
            return None

        port_health_info = {}
        for guest in self.nova.instances.values():
            for port in guest.ports:
                stats = port.stats
                if stats:
                    outliers = self._get_port_stat_outliers(stats)
                    if not outliers:
                        continue

                    if guest.uuid not in port_health_info:
                        port_health_info[guest.uuid] = {}

                    port_health_info[guest.uuid][port.hwaddr] = outliers

        if port_health_info:
            health = {'num-vms-checked': len(self.nova.instances),
                      'stats': port_health_info}
            return health

        return None
