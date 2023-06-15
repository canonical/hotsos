import abc
import re

from hotsos.core.log import log
from hotsos.core.search import (
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.plugins.kernel.kernlog.common import (
    CallTraceHeuristicBase,
    CallTraceStateBase,
    TraceTypeBase,
    KernLogBase,
)

KERNLOG_TS = r'\[\s*\d+\.\d+\]'
KERNLOG_PREFIX = (r'(?:\S+\s+\d+\s+[\d:]+\s+\S+\s+\S+:\s+)?{}'.
                  format(KERNLOG_TS))


class OOMTraceHeuristicCheckFreePages(CallTraceHeuristicBase):
    """
    Defines a basic memory check heuristic using information extracted from
    an OOM kill call trace.
    """

    def __init__(self, state):
        """
        @param state: an OOMCallTraceState object.
        """
        self.node = state.node_id
        self.zone = state.node_zone
        self.free = state.free
        self.min = state.min
        self.low = state.low

    def __call__(self):
        """
        Returns a list of strings representing failures.
        """
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


class OOMCallTraceState(CallTraceStateBase):

    def __repr__(self):
        """
        Provide a nice way to view the state e.g. in debug logs.
        """
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


class GenericTraceType(TraceTypeBase):
    """
    Used to identify call traces of any type.

    This is mainly useful for high level checks like whether or not any call
    traces have occurred.
    """

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

        # Very basic, just a simple expression to identify that a call trace
        # has occurred.
        expr = r'.+Call Trace:'
        self._search_def = SearchDef(expr, tag=self.name)
        return self._search_def

    def apply(self, results):
        """
        Run through the results.

        @param results: list of search.SearchResult objects.
        """
        log.debug("%s has %s results", self.__class__.__name__, len(results))
        for _trace in results:
            # just a save a value i.e. to make the list length represent the
            # number of call traces.
            self.generics.append(True)

    @property
    def heuristics(self):
        """
        Register any heuristics we want to run here.
        """
        return []

    def __len__(self):
        return len(self.generics)

    def __iter__(self):
        for generics in self.generics:
            yield generics


class MemFieldsBase(object):
    """
    Provides a common way to identify fields in an oom kill trace and extract
    their values.
    """

    def extract(self, part, line):
        for field in self.fields:
            ret = re.search('{}:{}'.format(field, self.expr), line)
            if ret:
                part.add(field, ret.group(1))

    @property
    @abc.abstractmethod
    def expr(self):
        """ Search pattern template used to match a field and its value. """

    @property
    @abc.abstractmethod
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


class BcacheDeadlockType(TraceTypeBase):

    def __init__(self):
        self._search_def = None
        self.deadlocks = []

    @property
    def name(self):
        return 'calltrace-bcache'

    @property
    def searchdef(self):
        if self._search_def:
            return self._search_def

        start = SearchDef(r'{}.+\s+task bcache-register:(\d+) blocked for '
                          r'more than (\d+) seconds.'.
                          format(KERNLOG_PREFIX))
        body = SearchDef(r'(\S+) schedule(\S+) closure_sync(\S+)'
                         r' bch_journal_meta(\S+) bch_btree_set_root(\S+)'
                         r' bch_journal_replay(\S+) register_bcache(\S+)')
        end = SearchDef(r'{}.+\s+do_syscall_(\S+)'.format(KERNLOG_PREFIX))
        self._search_def = SequenceSearchDef(start, tag='bcache', body=body,
                                             end=end)
        return self._search_def

    def apply(self, results):
        """
        Run through the results.
        @param results: list of search.SearchResult objects.
        """
        log.debug("%s has %s results", self.__class__.__name__, len(results))
        if len(results) > 0:
            # we have found at least one deadlock
            self.deadlocks.append(True)

    @property
    def heuristics(self):
        """
        Register any heuristics we want to run here.
        """
        return []

    def __len__(self):
        return len(self.deadlocks)

    def __iter__(self):
        for deadlocks in self.deadlocks:
            yield deadlocks


class FanotifyDeadlockType(TraceTypeBase):

    def __init__(self):
        self._search_def = None
        self.fanotify_hangs = []

    @property
    def name(self):
        return 'calltrace-fanotify'

    @property
    def searchdef(self):
        if self._search_def:
            return self._search_def

        start = SearchDef(r'.+ blocked for more than (\d+) seconds.')
        body = SearchDef(r'(\S+) schedule(\S+) fanotify_handle_event(\S+)'
                         r' fsnotify(\S+)')
        end = SearchDef(r'.+\s+do_sys_open(\S+)')
        self._search_def = SequenceSearchDef(start, tag='fanotify', body=body,
                                             end=end)
        return self._search_def

    def apply(self, results):
        """
        Run through the results.
        @param results: list of search.SearchResult objects.
        """
        log.debug("%s has %s results", self.__class__.__name__, len(results))
        if len(results) > 0:
            # we have found at least one fanotify related hang
            self.fanotify_hangs.append(True)

    @property
    def heuristics(self):
        """
        Register any heuristics we want to run here.
        """
        return []

    def __len__(self):
        return len(self.fanotify_hangs)

    def __iter__(self):
        for fanotify_hangs in self.fanotify_hangs:
            yield fanotify_hangs


class OOMKillerTraceType(TraceTypeBase):

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
        # NOTE: we need a better way to capture the different variations of
        #       the following message.
        end = SearchDef(r'{} '
                        r'(?:Out of memory: |Memory cgroup out of memory: )?'
                        r'Killed process (\d+) .+'.format(KERNLOG_PREFIX))
        self._search_def = SequenceSearchDef(start, tag='oom', body=body,
                                             end=end)
        return self._search_def

    def apply(self, results):
        log.debug("%s has %s results", self.__class__.__name__, len(results))
        for trace in results.values():
            oom_kill = OOMCallTraceState()
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
                        current_node = OOMCallTraceState()
                        node_id = ret.group(1)
                        current_node.add('node_id', node_id)
                        oom_kill.nodes[node_id] = {'main': current_node}
                    else:
                        ret = re.search(r"Node (\d+) (\S+) free:", line)
                        if ret:
                            current_node = OOMCallTraceState()
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


class HungtaskTraceType(TraceTypeBase):

    def __init__(self):
        self._search_def = None
        self.hungtasks = []

    @property
    def name(self):
        return 'calltrace-hungtask'

    @property
    def searchdef(self):
        if self._search_def:
            return self._search_def

        start = SearchDef(r'.+ blocked for more than (\d+) seconds.')
        body = SearchDef('.+')
        end = SearchDef(r'.+\s+do_syscall_(\S+)')
        self._search_def = SequenceSearchDef(start, tag='hungtask', body=body,
                                             end=end)
        return self._search_def

    def apply(self, results):
        """
        Run through the results.
        @param results: list of searchtools.SearchResult objects.
        """
        log.debug("%s has %s results", self.__class__.__name__, len(results))
        if len(results) > 0:
            # we have found at least one blocked task
            self.hungtasks.append(True)

    @property
    def heuristics(self):
        """
        Register any heuristics we want to run here.
        """
        return []

    def __len__(self):
        return len(self.hungtasks)

    def __iter__(self):
        for hungtasks in self.hungtasks:
            yield hungtasks


class CallTraceManager(KernLogBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # All trace types should be registered here.
        self.tracetypes = [GenericTraceType(), OOMKillerTraceType(),
                           BcacheDeadlockType(), HungtaskTraceType(),
                           FanotifyDeadlockType()]
        self.run()

    def run(self):
        for tracetype in self.tracetypes:
            self.searcher.add(tracetype.searchdef, self.path)

        self.results = self.searcher.run()
        for tracetype in self.tracetypes:
            if type(tracetype.searchdef) == SequenceSearchDef:
                results = self.results.find_sequence_sections(
                                                           tracetype.searchdef)
            else:
                results = self.results.find_by_tag(tracetype.searchdef.tag)

            tracetype.apply(results)

    def __getattr__(self, name):
        """
        If one or more trace has been identified with the given type name,
        return its object.
        """
        for h in self.tracetypes:
            if h.name == name.replace('_', '-'):
                return h
