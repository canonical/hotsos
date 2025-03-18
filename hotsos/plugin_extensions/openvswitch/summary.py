from hotsos.core.host_helpers import NetworkPort
from hotsos.core.plugins.openvswitch import OpenvSwitchChecks
from hotsos.core.plugins.openvswitch.ovn import OVNBase
from hotsos.core.plugins.openvswitch.ovs import OpenvSwitchBase
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class OpenvSwitchSummary(OpenvSwitchChecks):
    """ Implementation of OpenvSwitch summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ovs = OpenvSwitchBase()
        self.ovn = OVNBase()

    @summary_entry('config', get_min_available_entry_index())
    def summary_ovsdb_config(self):
        _config = {}
        if self.ovs.offload_enabled:
            _config['offload'] = 'enabled'

        _other_config = self.ovs.ovsdb.Open_vSwitch.other_config
        if _other_config:
            _config['other-config'] = _other_config

        _external_ids = self.ovs.ovsdb.Open_vSwitch.external_ids
        if _external_ids:
            _config['external-ids'] = _external_ids

        db_keys = ['inactivity_probe', 'max_backoff']
        for name, db in {'nbdb': self.ovn.nbdb, 'sbdb': self.ovn.sbdb}.items():
            if db:
                _config[name] = {}
                for key in db_keys:
                    val = getattr(db.Connection, key)
                    if val:
                        _config[name][key] = val

        return _config or None

    @summary_entry('bridges', get_min_available_entry_index() + 1)
    def summary_bridges(self):
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
                ports = [f"({len(ports)} ports)"]

            bridges[bridge.name] = ports

        return bridges or None

    @summary_entry('tunnels', get_min_available_entry_index() + 2)
    def summary_tunnels(self):
        return self.ovs.tunnels or None

    @summary_entry('ovn', get_min_available_entry_index() + 3)
    def summary_ovn_resources(self):
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

        return info or None
