from hotsos.core.host_helpers import NetworkPort
from hotsos.core.plugins.openvswitch import OpenvSwitchChecksBase
from hotsos.core.plugins.openvswitch.ovn import OVNBase
from hotsos.core.plugins.openvswitch.ovs import OpenvSwitchBase


class OpenvSwitchSummary(OpenvSwitchChecksBase):
    summary_part_index = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ovs = OpenvSwitchBase()
        self.ovn = OVNBase()

    def __0_summary_services(self):
        """Get string info for running daemons."""
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

    def __1_summary_dpkg(self):
        return self.apt.all_formatted

    def __2_summary_config(self):
        _config = {}
        if self.ovs.offload_enabled:
            _config['offload'] = 'enabled'

        _other_config = self.ovs.ovsdb.Open_vSwitch.other_config
        if _other_config:
            _config['other-config'] = _other_config

        _external_ids = self.ovs.ovsdb.Open_vSwitch.external_ids
        if _external_ids:
            _config['external-ids'] = _external_ids

        if _config:
            return _config

    def __3_summary_bridges(self):
        bridges = {}
        for bridge in self.ovs.bridges:
            # filter patch/phy ports since they are not generally interesting
            ports = []
            for port in bridge.ports:
                if not isinstance(port, NetworkPort):
                    name = port
                else:
                    name = port.name

                if (name.startswith('patch-') or name.startswith('phy-') or
                        name.startswith('int-')):
                    continue

                if not isinstance(port, NetworkPort):
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

    def __4_summary_tunnels(self):
        if self.ovs.tunnels:
            return self.ovs.tunnels

    def __5_summary_ovn(self):
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
