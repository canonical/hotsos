#!/usr/bin/python3
import re
import os

from common import (
    constants,
    cli_helpers,
)
from common.searchtools import (
    SearchDef,
    SequenceSearchDef,
    FileSearcher,
)
from common.utils import mktemp_dump
from openstack_common import OpenstackChecksBase


CONFIG = {"nova": [{"path": os.path.join(constants.DATA_ROOT,
                                         "etc/nova/nova.conf"),
                    "key": "my_ip"}],
          "neutron": [{"path":
                       os.path.join(constants.DATA_ROOT,
                                    "etc/neutron/plugins/ml2/"
                                    "openvswitch_agent.ini"),
                       "key": "local_ip"}]}
YAML_PRIORITY = 4


class OpenstackNetworkChecks(OpenstackChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.neutron_phy_ports = []
        out = cli_helpers.get_ip_link_show()
        self.f_ip_link_show = mktemp_dump(''.join(out))

    @property
    def output(self):
        if self._output:
            return {"network": self._output}

    def __del__(self):
        if os.path.exists(self.f_ip_link_show):
            os.unlink(self.f_ip_link_show)

    def _find_line(self, key, lines):
        for i, line in enumerate(lines):
            if re.compile(key).match(line):
                return i

        return None

    def _find_interface_name_by_ip_address(self, ip_address):
        """Lookup interface by name in ip addr show"""
        iface = None
        lines = cli_helpers.get_ip_addr()
        a = self._find_line(r".+{}.+".format(ip_address), lines)
        while True:
            ret = re.compile(r"^[0-9]+:\s+(\S+):\s+.+"
                             ).match(lines[a])
            if ret:
                iface = ret[1]
                break

            a = a-1

        return iface

    def get_config_network_info(self):
        """For each service defined, check its config file and extract network
        info e.g. neutron local_ip is address of interface used for creating
        tunnels (vxlan, gre etc) and nova my_ip is interface used by-default
        for vm migration.
        """
        config_info = {}
        for svc in CONFIG:
            for info in CONFIG[svc]:
                data_source = info["path"]
                key = info["key"]
                if not os.path.exists(data_source):
                    continue

                iface = None
                ip_address = None
                for line in open(data_source).readlines():
                    ret = re.compile(r"^\s*{}\s*=\s*([0-9\.]+).*".
                                     format(key)).match(line)
                    if ret:
                        ip_address = ret[1]
                        iface = self._find_interface_name_by_ip_address(
                                                                    ip_address)
                        if iface:
                            break

                if svc not in config_info:
                    config_info[svc] = {}

                if svc == "neutron" and iface:
                    self.neutron_phy_ports.append(iface)

                if ip_address:
                    config_info[svc][key] = "{} ({})".format(ip_address, iface)
                else:
                    config_info[svc][key] = None

        if config_info:
            self._output["config"] = config_info

    def get_ns_info(self):
        """Populate namespace information dict."""
        ns_info = {}
        for line in cli_helpers.get_ip_netns():
            ret = re.compile(r"^([a-z0-9]+)-([0-9a-z\-]+)\s+.+").match(line)
            if ret:
                if ret[1] in ns_info:
                    ns_info[ret[1]] += 1
                else:
                    ns_info[ret[1]] = 1

        if ns_info:
            self._output["namespaces"] = ns_info

    def _get_instances_info(self):
        """Get information e.g. ip link  stats for each port on a vm"""
        instances = self.running_instances
        if instances is None:
            return

        guest_info = {}
        ps_output = cli_helpers.get_ps()
        for uuid in instances:
            for line in ps_output:
                expr = r".+guest=(\S+),.+product=OpenStack Nova.+uuid={}.+"
                ret = re.compile(expr.format(uuid)).match(line)
                if ret:
                    guest = ret[1]
                    if guest not in guest_info:
                        guest_info[uuid] = {"ports": []}

                    ret = re.compile(r"mac=([a-z0-9:]+)").findall(line)
                    if ret:
                        if "ports" not in guest_info[uuid]:
                            guest_info[uuid]["ports"] = []

                        for port in ret:
                            guest_info[uuid]["ports"].append({"mac": port,
                                                              "health": {}})

        return guest_info

    def _get_port_stats(self, name=None, mac=None):
        """Get ip link stats for the given port."""
        stats_raw = []

        if mac:
            libvirt_mac = "fe" + mac[2:]

        exprs = []
        if mac:
            for _mac in [mac, libvirt_mac]:
                exprs.append(r"^\s+link/ether\s+({})\s+.+".format(_mac))
        else:
            exprs.append(r"^\d+:\s+({}):\s+.+".format(name))

        s = FileSearcher()
        sd = SequenceSearchDef(
                    # match start of interface
                    start=SearchDef(exprs),
                    # match body of interface
                    body=SearchDef(r".+"),
                    # match next interface or EOF
                    end=SearchDef([r"^\d+:\s+\S+:.+", r"^$"]),
                    tag="ifaces")
        s.add_search_term(sd, path=self.f_ip_link_show)
        results = s.search()
        for results in results.find_sequence_sections(sd).values():
            for result in results:
                if result.tag == sd.body_tag:
                    stats_raw.append(result.get(0))

            # stop at first match - if matching by mac address it is
            # possible for multiple interfaces to have the same mac e.g.
            # bonds and its interfaces but we dont support that so just use
            # first.
            break

        stats = {}
        counters = {}
        if stats_raw:
            for i, line in enumerate(stats_raw):
                ret = re.compile(r"\s+([RT]X):\s+.+").findall(line)
                if ret:
                    rxtx = ret[0].lower()
                    ret = re.compile(r"\s*([a-z]+)\s*").findall(line)
                    if ret:
                        for j, column in enumerate(ret):
                            value = int(stats_raw[i + 1].split()[j])
                            for key in ["packets", "dropped", "errors",
                                        "overrun"]:
                                if column == key:
                                    if rxtx not in counters:
                                        counters[rxtx] = {}

                                    counters[rxtx][key] = float(value)
                                    continue

        if counters:
            for rxtx in counters:
                total = sum(counters[rxtx].values())
                del counters[rxtx]["packets"]
                for key, value in counters[rxtx].items():
                    if value:
                        pcent = int(100 / total * value)
                        if pcent <= 1:
                            continue

                        if rxtx not in stats:
                            stats[rxtx] = {}

                        stats[rxtx][key] = "{} ({}%)".format(int(value), pcent)

        return stats

    def get_instances_port_health(self):
        instances = self._get_instances_info()
        if not instances:
            return

        port_health_info = {}
        for uuid in instances:
            for port in instances[uuid]['ports']:
                stats = self._get_port_stats(mac=port["mac"])
                if stats:
                    if uuid not in port_health_info:
                        port_health_info[uuid] = {}
                    port_health_info[uuid][port["mac"]] = stats

        if port_health_info:
            health = {"vm-ports": {"num-vms-checked": len(instances),
                                   "stats": port_health_info}}
            if "port-health" in self._output:
                self._output["port-health"].update(health)
            else:
                self._output["port-health"] = health

    def get_neutron_phy_port_health(self):
        port_health_info = {}
        for port in self.neutron_phy_ports:
            stats = self._get_port_stats(name=port)
            if stats:
                port_health_info[port] = stats

        if port_health_info:
            health = {"phy-ports": port_health_info}
            if "port-health" in self._output:
                self._output["port-health"].updated(health)
            else:
                self._output["port-health"] = health

    def __call__(self):
        self.get_ns_info()
        self.get_config_network_info()
        self.get_neutron_phy_port_health()
        self.get_instances_port_health()
