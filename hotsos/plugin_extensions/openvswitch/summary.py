from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.host_helpers import NetworkPort
from hotsos.core.plugins.openvswitch import OpenvSwitchChecksBase
from hotsos.core.plugins.openvswitch.ovs import OpenvSwitchBase
from hotsos.core.plugins.openvswitch.ovn import OVNBase


class OpenvSwitchSummary(OpenvSwitchChecksBase):

    def __init__(self):
        super().__init__()
        self.ovs = OpenvSwitchBase()
        self.ovn = OVNBase()

    @idx(0)
    def __summary_services(self):
        """Get string info for running daemons."""
        if self.systemd.services:
            return self.systemd.summary
        elif self.pebble.services:
            return self.pebble.summary

    @idx(1)
    def __summary_dpkg(self):
        return self.apt.all_formatted

    @idx(2)
    def __summary_config(self):
        _config = {}
        if self.ovs.offload_enabled:
            _config['offload'] = 'enabled'

        if self.ovs.ovsdb.other_config:
            _config['other-config'] = self.ovs.ovsdb.other_config

        if self.ovs.ovsdb.external_ids:
            _config['external-ids'] = self.ovs.ovsdb.external_ids

        if _config:
            return _config

    @idx(3)
    def __summary_bridges(self):
        bridges = {}
        for bridge in self.ovs.bridges:
            # filter patch/phy ports since they are not generally interesting
            ports = []
            for port in bridge.ports:
                if type(port) != NetworkPort:
                    name = port
                else:
                    name = port.name

                if (name.startswith('patch-') or name.startswith('phy-') or
                        name.startswith('int-')):
                    continue

                if type(port) != NetworkPort:
                    # ovs port so will be just a name
                    ports.append(port)
                    continue

                ports.append(port.to_dict())

            # show total count for br-int since it can have a very large number
            if bridge.name == 'br-int' and ports:
                ports = ["({} ports)".format(len(ports))]

            bridges[bridge.name] = ports

        if bridges:
            return bridges

    @idx(4)
    def __summary_tunnels(self):
        if self.ovs.tunnels:
            return self.ovs.tunnels

    @idx(5)
    def __summary_ovn(self):
        info = {}
        if self.ovn.nbdb:
            routers = self.ovn.nbdb.routers
            switches = self.ovn.nbdb.switches
            info['nbdb'] = {'routers': len(routers),
                            'switches': len(switches)}

        if self.ovn.sbdb:
            ports = []
            cr_ports = []
            for c in self.ovn.sbdb.chassis:
                ports.extend(c.ports)
                cr_ports.extend(c.cr_ports)

            info['sbdb'] = {'chassis': len(self.ovn.sbdb.chassis),
                            'ports': len(ports),
                            'router-gateways': len(cr_ports)}

        if info:
            return info
