import re
from functools import cached_property

from hotsos.core.factory import FactoryBase
from hotsos.core.log import log
from hotsos.core.host_helpers import (
    CLIHelper,
    CLIHelperFile,
    HostNetworkingHelper
)
from hotsos.core.search import FileSearcher, SearchDef


class OVSDBTable(object):
    """
    Provides an interface to an OVSDB table. Records can be extracted from
    either 'get' or 'list' command outputs. We try 'get' first and of not found
    we search in output of 'list'.
    """

    def __init__(self, name):
        self.name = name

    def _convert_record_to_dict(self, record):
        """ Convert the ovsdb record dict format to a python dictionary. """
        out = {}
        if not record or record == '{}':
            return out

        expr = r'(\S+="[^"]+"|\S+=\S+),? ?'
        for field in re.compile(expr).findall(record):
            for char in [',', '}', '{']:
                field = field.strip(char)

            key, _, val = field.partition('=')
            out[key] = val.strip('"')

        return out

    def _get_cmd(self, table):
        return lambda **kwargs: CLIHelper().ovs_vsctl_get(table=table,
                                                          **kwargs)

    def _list_cmd(self, table):
        return lambda **kwargs: CLIHelper().ovs_vsctl_list(table=table,
                                                           **kwargs)

    def _fallback_query(self, column):
        """ Find first occurrence of column and return it. """
        for cmd in [self._list_cmd(self.name),
                    self._list_cmd(self.name.lower())]:
            for line in cmd():
                if line.startswith('{} '.format(column)):
                    return line.partition(':')[2].strip()

    def get(self, record, column):
        """
        Try to get column using get command and failing that, try getting it
        from list.
        """
        value = self._get_cmd(self.name)(record=record, column=column)
        if not value:
            value = self._fallback_query(column=column)

        return self._convert_record_to_dict(value)

    def __getattr__(self, column):
        """ Get column for special records i.e. with key '.' """
        return self.get(record='.', column=column)


class OVSDB(FactoryBase):
    """
    This class is used like a factory in that attributes are table names that
    return OVSDBTable objects on which attributes are row values.
    """
    def __getattr__(self, table):
        return OVSDBTable(table)


class OVSDPLookups(object):

    def __init__(self):
        cli = CLIHelper()
        out = cli.ovs_appctl(command='dpctl/show', flags='-s',
                             args='system@ovs-system')
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
        for line in self.cli.ovs_ofctl(command='show', args=self.name):
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
        ovn_external_ids = self.ovsdb.Open_vSwitch.external_ids
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
                  cli.ovs_appctl(command='ofproto/list-tunnels'))
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

        for proto, values in tunnel_info.items():
            local_addr = values['local']
            if local_addr:
                iface = nethelp.get_interface_with_addr(local_addr)
                if iface:
                    values['iface'] = iface.to_dict()
                    del values['local']
                else:
                    log.info("could not find interface for address '%s'",
                             local_addr)

            if 'remotes' not in values:
                log.info('no remote tunnel endpoints found for proto=%s',
                         proto)
                num_remotes = 0
            else:
                num_remotes = len(values['remotes'])

            values['remotes'] = num_remotes

        return tunnel_info

    @cached_property
    def offload_enabled(self):
        config = self.ovsdb.Open_vSwitch.other_config
        if not config:
            return False

        if config.get('hw-offload') == "true":
            return True

        return False


class OVSDPDK(OpenvSwitchBase):

    @cached_property
    def config(self):
        return self.ovsdb.Open_vSwitch.other_config or {}

    @property
    def enabled(self):
        if self.config.get('dpdk-init') == "true":
            return True

        return False

    @property
    def pmd_cpu_mask(self):
        mask = self.config.get('pmd-cpu-mask')
        if mask is not None:
            return int(mask, 16)

    @property
    def dpdk_lcore_mask(self):
        mask = self.config.get('dpdk-lcore-mask')
        if mask is not None:
            return int(mask, 16)
