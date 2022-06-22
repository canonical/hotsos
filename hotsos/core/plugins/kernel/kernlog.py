import abc
import os
import re

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.host_helpers import CLIHelper, HostNetworkingHelper
from hotsos.core.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)

KERNLOG_TS = r'\[\s*\d+\.\d+\]'
KERNLOG_PREFIX = (r'(?:\S+\s+\d+\s+[\d:]+\s+\S+\s+\S+:\s+)?{}'.
                  format(KERNLOG_TS))


class CallTraceHeuristicBase(object):

    @abc.abstractmethod
    def __call__(self):
        """ """


class OOMTraceHeuristicCheckFreePages(CallTraceHeuristicBase):

    def __init__(self, state):
        self.node = state.node_id
        self.zone = state.node_zone
        self.free = state.free
        self.min = state.min
        self.low = state.low

    def __call__(self):
        fails = []
        if self.free < self.min:
            fails.append("Node {} zone {} free pages {} below "
                         "min {}".format(self.node, self.zone, self.free,
                                         self.min))
        elif self.free < self.low:
            fails.append("Node {} zone {} free pages {} below "
                         "low {}".format(self.node, self.zone, self.free,
                                         self.low))

        return fails


class CallTraceState(object):

    def __init__(self):
        self._info = {}

    def add(self, key, value):
        self._info[key] = value

    def __getattr__(self, key):
        return self._info.get(key)

    def __repr__(self):
        prefix = ""
        if self.node_id:
            prefix = " -> "

        s = []
        for k, v in self._info.items():
            if k == 'nodes':
                s.append("{}{}:".format(prefix, k))
                for node, zones in v.items():
                    s.append(">> node{}".format(node))
                    for zone, fields in zones.items():
                        s.append(" {}: {}".format(zone, repr(fields)))
            else:
                s.append("{}{}: {}".format(prefix, k, v))

        return "\n{}\n".format('\n'.join(s))


class TraceHandlerBase(abc.ABC):

    @abc.abstractproperty
    def name(self):
        """
        Name used to identify the type of call trace e.g. "oomkiller".
        """

    @abc.abstractproperty
    def searchdef(self):
        """
        A search definition object (simple or sequence) used to identify this
        call trace.
        """

    @abc.abstractmethod
    def apply(self, results):
        """
        Take results and parse into constituent parts.

        @param results: a SearchResultsCollection object containing the results
        of our search.
        """

    @abc.abstractproperty
    def heuristics(self):
        """ Return a list of CallTraceHeuristic objects. """

    @abc.abstractmethod
    def __len__(self):
        """ Return number of call stacks identified.  """

    @abc.abstractmethod
    def __iter__(self):
        """ Iterate over each call trace found. """


class GenericTraceHandler(TraceHandlerBase):

    def __init__(self):
        self._search_def = None
        self.generics = []

    @property
    def name(self):
        return 'calltrace-anytype'

    @property
    def searchdef(self):
        if self._search_def:
            return self._search_def

        expr = r'.+Call Trace:'
        self._search_def = SearchDef(expr, tag=self.name)
        return self._search_def

    def apply(self, result):
        for trace in result:
            part = CallTraceState()
            part.add('calltrace', trace.get(0))
            self.generics.append(part)

    @property
    def heuristics(self):
        return []

    def __len__(self):
        return len(self.generics)

    def __iter__(self):
        for generics in self.generics:
            yield generics


class MemFieldsBase(object):

    @property
    def buddy_allocator_sizes(self):
        return [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]

    def extract(self, part, line):
        for field in self.fields:
            ret = re.search('{}:{}'.format(field, self.expr), line)
            if ret:
                part.add(field, ret.group(1))

    @abc.abstractproperty
    def expr(self):
        """ Search pattern template used to match a field and its value. """

    @abc.abstractproperty
    def fields(self):
        """ List of fields we want extract from a given section. """


class MemFieldsMain(MemFieldsBase):

    @property
    def expr(self):
        return r'\s?(\d+)'

    @property
    def fields(self):
        return ['active_anon', 'inactive_anon', 'isolated_anon',
                'active_file', 'inactive_file', 'isolated_file', 'unevictable',
                'dirty', 'writeback', 'slab_reclaimable', 'slab_unreclaimable',
                'mapped', 'shmem', 'pagetables', 'bounce', 'free', 'free_pcp',
                'free_cma']


class MemFieldsNodeMem(MemFieldsBase):

    @property
    def expr(self):
        return r'\s?(\d+)kB'

    @property
    def fields(self):
        # not all kernels have all these fields
        return ['active_anon', 'inactive_anon', 'active_file',
                'inactive_file', 'unevictable', r'isolated\(anon\)',
                r'isolated\(file\)', 'mapped', 'dirty', 'writeback', 'shmem',
                'shmem_thp', 'shmem_pmdmapped', 'anon_thp', 'writeback_tmp',
                'kernel_stack', 'pagetables', 'writeback_tmp', 'unstable']


class MemFieldsNodeUNRC(MemFieldsBase):

    @property
    def expr(self):
        return r'\s?([a-z]+)$'

    @property
    def fields(self):
        return [r'all_unreclaimable\?']


class MemFieldsNodeZoneMem(MemFieldsBase):

    @property
    def expr(self):
        return r'\s?(\d+)[Kk]B'

    @property
    def fields(self):
        return ['free', 'min', 'low', 'high',
                'reserved_highatomic', 'active_anon', 'inactive_anon',
                'active_file', 'inactive_file', 'unevictable', 'writepending',
                'present', 'managed', 'mlocked', 'bounce', 'free_pcp',
                'local_pcp', 'free_cma']


class OOMKillerTraceHandler(TraceHandlerBase):

    def __init__(self):
        self._search_def = None
        self.oom_traces = []

    @property
    def name(self):
        return 'oom-killer'

    @property
    def searchdef(self):
        if self._search_def:
            return self._search_def

        start = SearchDef(r'{} (\S+) invoked oom-killer: .+, '
                          r'order=([+-]?\d+),.+'.
                          format(KERNLOG_PREFIX))
        body = SearchDef('.+')
        end = SearchDef(r'{} Out of memory: Killed process (\d+) .+'.
                        format(KERNLOG_PREFIX))
        self._search_def = SequenceSearchDef(start, tag='oom', body=body,
                                             end=end)
        return self._search_def

    def apply(self, result):
        for trace in result.values():
            oom_kill = CallTraceState()
            oom_kill.add('nodes', {})
            current_node = None
            for item in trace:
                if item.tag.endswith('-start'):
                    oom_kill.add('procname', item.get(1))
                    oom_kill.add('order', item.get(2))
                elif item.tag.endswith('-body'):
                    # There will be one or more of these.
                    line = item.get(0)

                    ret = re.search(r"Node (\d+) active_anon:", line)
                    if ret:
                        current_node = CallTraceState()
                        node_id = ret.group(1)
                        current_node.add('node_id', node_id)
                        oom_kill.nodes[node_id] = {'main': current_node}
                    else:
                        ret = re.search(r"Node (\d+) (\S+) free:", line)
                        if ret:
                            current_node = CallTraceState()
                            node_id = ret.group(1)
                            node_zone = ret.group(2)
                            current_node.add('node_id', node_id)
                            current_node.add('node_zone', node_zone)
                            oom_kill.nodes[node_id][node_zone] = current_node

                    if not current_node:
                        MemFieldsMain().extract(oom_kill, line)
                    elif current_node.node_zone:
                        MemFieldsNodeZoneMem().extract(current_node, line)
                    else:
                        MemFieldsNodeMem().extract(current_node, line)
                        MemFieldsNodeUNRC().extract(current_node, line)
                else:
                    # end
                    oom_kill.add('pid', item.get(1))

            log.info(oom_kill)
            self.oom_traces.append(oom_kill)

    @property
    def num_traces(self):
        return len(self.oom_traces)

    @property
    def heuristics(self):
        _heuristics = []
        for oom_trace in self.oom_traces:
            for node, zones in oom_trace.nodes.items():
                if node is None:
                    continue

                for zone, state in zones.items():
                    if zone == 'main':
                        continue

                    _heuristics.append(OOMTraceHeuristicCheckFreePages(state))

        return _heuristics

    def __len__(self):
        return len(self.oom_traces)

    def __iter__(self):
        for oom_trace in self.oom_traces:
            yield oom_trace


class KernLogBase(object):

    def __init__(self):
        self.searcher = FileSearcher()
        self.hostnet_helper = HostNetworkingHelper()
        self.cli_helper = CLIHelper()

    @property
    def path(self):
        return os.path.join(HotSOSConfig.DATA_ROOT, 'var/log/kern.log')


class CallTrace(KernLogBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handlers = [OOMKillerTraceHandler(),
                         GenericTraceHandler()]
        for handler in self.handlers:
            self.searcher.add_search_term(handler.searchdef, self.path)

        self.results = self.searcher.search()
        for handler in self.handlers:
            if type(handler.searchdef) == SequenceSearchDef:
                result = self.results.find_sequence_sections(handler.searchdef)
            else:
                result = self.results.find_by_tag(handler.searchdef.tag)

            handler.apply(result)

    def __getattr__(self, name):
        for h in self.handlers:
            if h.name == name.replace('_', '-'):
                return h


class OverMTUDroppedPacketEvent(object):

    @property
    def searchdef(self):
        return SearchDef(r'.+\] (\S+): dropped over-mtu packet',
                         hint='dropped', tag='over-mtu-dropped')


class KernLogEvents(KernLogBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for event in [OverMTUDroppedPacketEvent()]:
            self.searcher.add_search_term(event.searchdef, self.path)

        self.results = self.searcher.search()

    @property
    def over_mtu_dropped_packets(self):
        interfaces = {}
        for r in self.results.find_by_tag('over-mtu-dropped'):
            if r.get(1) in interfaces:
                interfaces[r.get(1)] += 1
            else:
                interfaces[r.get(1)] = 1

        if interfaces:
            # only report on interfaces that currently exist
            host_interfaces = [iface.name for iface in
                               self.hostnet_helper.host_interfaces_all]
            # filter out interfaces that are actually ovs bridge aliases
            ovs_bridges = self.cli_helper.ovs_vsctl_list_br()
            # strip trailing newline chars
            ovs_bridges = [br.strip() for br in ovs_bridges]

            interfaces_extant = {}
            for iface in interfaces:
                if iface in host_interfaces:
                    if iface not in ovs_bridges:
                        interfaces_extant[iface] = interfaces[iface]
                    else:
                        log.debug("excluding ovs bridge %s", iface)

            if interfaces_extant:
                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(interfaces_extant.items(),
                                   key=lambda e: e[1], reverse=True):
                    sorted_dict[k] = v

                return sorted_dict
