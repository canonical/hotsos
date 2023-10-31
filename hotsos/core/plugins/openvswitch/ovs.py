import re
from functools import cached_property

from hotsos.core.log import log
from hotsos.core.host_helpers import (
    CLIHelper,
    CLIHelperFile,
    HostNetworkingHelper
)
from hotsos.core.search import FileSearcher, SearchDef


class OVSDB(object):

    def __init__(self):
        self.cli = CLIHelper()

    def _record_to_dict(self, record):
        record_dict = {}
        if record and record != '{}':
            expr = r'(\S+="[^"]+"|\S+=\S+),? ?'
            for field in re.compile(expr).findall(record):
                for char in [',', '}', '{']:
                    field = field.strip(char)

                key, _, val = field.partition('=')
                record_dict[key] = val.strip('"')

        return record_dict

    def __getattr__(self, db_record):
        """ Dynamically request db records. """
        value = self.cli.ovs_vsctl_get_Open_vSwitch(record=db_record)
        if db_record == 'external_ids' and not value:
            for line in self.cli.ovs_vsctl_list_Open_vSwitch():
                if line.startswith('external_ids '):
                    value = line.partition(':')[2].strip()
                    break

        if value:
            return self._record_to_dict(value)


class OVSDPLookups(object):

    def __init__(self):
        cli = CLIHelper()
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
        self.cli = CLIHelper()
        self.nethelper = nethelper

    @cached_property
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
        self.ovsdb = OVSDB()

    @cached_property
    def bridges(self):
        bridges = self.cli.ovs_vsctl_list_br()
        return [OVSBridge(br.strip(), self.net_helper) for br in bridges]

    @cached_property
    def tunnels(self):
        tunnel_info = {}
        ovn_external_ids = self.ovsdb.external_ids
        if ovn_external_ids:
            # ovn only shows the local ip used in the db so we have to get from
            # there.
            proto = ovn_external_ids.get('ovn-encap-type')
            if proto:
                local_addr = ovn_external_ids['ovn-encap-ip']
                tunnel_info[proto] = {'local': local_addr}

        nethelp = HostNetworkingHelper()
        with CLIHelperFile() as cli:
            s = FileSearcher()
            expr = r'.+ \(([a-z]+): ([a-f\d\.:]+)->([a-f\d\.:]+), .+'
            s.add(SearchDef(expr, tag='all'),
                  cli.ovs_appctl_ofproto_list_tunnels())
            results = s.run()
            for r in results.find_by_tag('all'):
                proto = r.get(1)
                if proto not in tunnel_info:
                    tunnel_info[proto] = {}

                if 'remotes' not in tunnel_info[proto]:
                    tunnel_info[proto]['remotes'] = []

                if 'local' not in tunnel_info[proto]:
                    tunnel_info[proto]['local'] = r.get(2)

                tunnel_info[proto]['remotes'].append(r.get(3))

        for proto in tunnel_info:
            local_addr = tunnel_info[proto]['local']
            if local_addr:
                iface = nethelp.get_interface_with_addr(local_addr)
                if iface:
                    tunnel_info[proto]['iface'] = iface.to_dict()
                    del tunnel_info[proto]['local']
                else:
                    log.info("could not find interface for address '%s'",
                             local_addr)

            if 'remotes' not in tunnel_info[proto]:
                log.info('no remote tunnel endpoints found for proto=%s',
                         proto)
                num_remotes = 0
            else:
                num_remotes = len(tunnel_info[proto]['remotes'])

            tunnel_info[proto]['remotes'] = num_remotes

        return tunnel_info

    @cached_property
    def offload_enabled(self):
        config = self.ovsdb.other_config
        if not config:
            return False

        if config.get('hw-offload') == "true":
            return True

        return False

    @cached_property
    def dpdk_enabled(self):
        config = self.ovsdb.other_config
        if not config:
            return False

        if config.get('dpdk-init') == "true":
            return True

        return False
