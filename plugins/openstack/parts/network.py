#!/usr/bin/python3
import re
import os

from common import (
    constants,
    helpers,
    plugin_yaml,
)

CONFIG = {"nova": [{"path": os.path.join(constants.DATA_ROOT,
                                         "etc/nova/nova.conf"),
                    "key": "my_ip"}],
          "neutron": [{"path":
                       os.path.join(constants.DATA_ROOT,
                                    "etc/neutron/plugins/ml2/"
                                    "openvswitch_agent.ini"),
                       "key": "local_ip"}]}
NETWORK_INFO = {}


def find_line(key, lines):
    for i, line in enumerate(lines):
        if re.compile(key).match(line):
            return i

    return None


def find_interface_name_by_ip_address(ip_address):
    """Lookup interface by name in ip addr show"""
    iface = None
    lines = helpers.get_ip_addr()
    a = find_line(r".+{}.+".format(ip_address), lines)
    while True:
        ret = re.compile(r"^[0-9]+:\s+(\S+):\s+.+"
                         ).match(lines[a])
        if ret:
            iface = ret[1]
            break

        a = a-1

    return iface


def get_config_network_info():
    """For each service defined, check its config file and extract network
    info e.g. neutron local_ip is address of interface used for creating
    tunnels (vxlan, gre etc) and nova my_ip is interface used by-default for
    vm migration.
    """
    config_info = {}
    port_stats_info = {}
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
                    iface = find_interface_name_by_ip_address(ip_address)
                    if iface:
                        break

            if svc not in config_info:
                config_info[svc] = {}

            if ip_address:
                config_info[svc][key] = "{} ({})".format(ip_address, iface)
                stats = get_port_stats(name=iface)
                if stats:
                    port_stats_info[iface] = stats
            else:
                config_info[svc][key] = None

    if config_info:
        NETWORK_INFO["config"] = config_info

    if port_stats_info:
        NETWORK_INFO["stats"] = port_stats_info


def get_ns_info():
    """Populate namespace information dict."""
    ns_info = {}
    for line in helpers.get_ip_netns():
        ret = re.compile(r"^([a-z0-9]+)-([0-9a-z\-]+)\s+.+").match(line)
        if ret:
            if ret[1] in ns_info:
                ns_info[ret[1]] += 1
            else:
                ns_info[ret[1]] = 1

    if ns_info:
        NETWORK_INFO["namespaces"] = ns_info


def get_instances_info():
    """Get information e.g. ip link  stats for each port on a vm"""
    master_plugin_plugin_yaml = plugin_yaml.get_master_plugin_yaml(
                                                         constants.PLUGIN_NAME)
    instances = master_plugin_plugin_yaml.get("instances")
    if instances is None:
        return

    guest_info = {}
    ps_output = helpers.get_ps()
    for uuid in instances:
        for line in ps_output:
            ret = re.compile(r".+guest=(\S+),.+product=OpenStack Nova.+uuid={}"
                             r".+".format(uuid)).match(line)
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


def get_port_stats(name=None, mac=None):
    """Get ip link stats for the given port."""
    ip_link_show = helpers.get_ip_link_show()
    mark = -1
    stats_raw = ""

    if mac:
        libvirt_mac = "fe" + mac[2:]

    for i, line in enumerate(ip_link_show):
        if mark < 0:
            if mac:
                for _mac in [mac, libvirt_mac]:
                    ret = re.compile(r"^\s+link/ether\s+{}\s+.+".format(_mac)
                                     ).match(line)
                    if ret:
                        mark = i
                        break
            else:
                ret = re.compile(r"^[0-9]+:\s+{}:\s+.+".format(name)
                                 ).match(line)
                if ret:
                    mark = i
        else:
            ret = re.compile(r"^[0-9]+:\s+.+").match(line)
            if ret:
                for n in range(mark, i):
                    stats_raw += ip_link_show[n]

                break

    stats = {}
    total_packets = float(0)
    if stats_raw:
        stats_raw = stats_raw.split("\n")
        for i, line in enumerate(stats_raw):
            ret = re.compile(r"\s+[RT]X:\s+.+").findall(line)
            if ret:
                ret = re.compile(r"\s*([a-z]+)\s*").findall(line)
                if ret:
                    for j, column in enumerate(ret):
                        value = int(stats_raw[i + 1].split()[j])
                        if column == "packets":
                            total_packets = float(value)
                            continue

                        for key in ["dropped", "errors"]:
                            if column == key:
                                if not value:
                                    continue

                                percentage = int((100/total_packets) * value)
                                # only report if > 0% drops/errors
                                if percentage > 0:
                                    stats[key] = "{} ({}%)".format(value,
                                                                   percentage)

    return stats


def get_instances_port_health():
    instances = get_instances_info()
    if not instances:
        return

    port_health_info = {}
    for uuid in instances:
        for port in instances[uuid]['ports']:
            stats = get_port_stats(mac=port["mac"])
            if stats:
                if uuid not in port_health_info:
                    port_health_info[uuid] = {}
                port_health_info[uuid][port["mac"]] = stats

    if port_health_info:
        NETWORK_INFO["port-health"] = {"num-vms-checked": len(instances),
                                       "stats": port_health_info}


if __name__ == "__main__":
    get_ns_info()
    get_config_network_info()
    get_instances_port_health()
    if NETWORK_INFO:
        NETWORK_INFO = {"network": NETWORK_INFO}
        plugin_yaml.save_part(NETWORK_INFO, priority=4)
