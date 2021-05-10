#!/usr/bin/python3
import re

from common import helpers

IP_ADDR_IFACE_NAME_EXPR = r"^[0-9]+:\s+(\S+):\s+.+"


class HostNetworkingHelper(object):

    def _get_interface_names(self, lines):
        _interfaces = []
        cexpr = re.compile(IP_ADDR_IFACE_NAME_EXPR)
        for line in lines:
            ret = cexpr.match(line)
            if ret:
                _interfaces.append(ret.group(1))

        return _interfaces

    def get_host_interfaces(self, include_namespaces=False):
        """Returns a list of all interfaces on the host including ones found in
        namespaces created with ip netns.
        """
        _interfaces = []
        _interfaces += self._get_interface_names(helpers.get_ip_addr())
        if not include_namespaces:
            return _interfaces

        for ns in helpers.get_ip_netns():
            ns_name = ns.partition(" ")[0]
            _interfaces += self._get_interface_names(
                                        helpers.get_ip_addr(namespace=ns_name))

        return _interfaces

    def host_interface_exists(self, iface, check_namespaces=True):
        _interfaces = self._get_interface_names(helpers.get_ip_addr())
        if iface in _interfaces:
            return True

        if not check_namespaces:
            return False

        for ns in helpers.get_ip_netns():
            interfaces = self._get_interface_names(
                                             helpers.get_ip_addr(namespace=ns))
            if iface in interfaces:
                return True

        return False
