import abc
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, HostNetworkingHelper
from hotsos.core.search import (
    CommonTimestampMatcher,
    FileSearcher,
    SearchConstraintSearchSince,
)

KERNLOG_TS = r'\[\s*\d+\.\d+\]'
KERNLOG_PREFIX = rf'(?:\S+\s+\d+\s+[\d:]+\s+\S+\s+\S+:\s+)?{KERNLOG_TS}'


class CallTraceHeuristicBase():
    """ Defines a common interface for heuristics implementations. """

    @abc.abstractmethod
    def __call__(self):
        """ Ensure callable to get results. """


class CallTraceStateBase():
    """
    A state capture object that allows getting and setting arbitrary state.
    """

    def __init__(self):
        self._info = {}

    def add(self, key, value):
        self._info[key] = value

    def __getattr__(self, key):
        return self._info.get(key)


class TraceTypeBase(abc.ABC):
    """
    This defines a common interface to trace types and should be implemented
    for any trace types we want to capture. Implementations of this object
    are typically registered with a CallTraceManager for processing.
    """

    @property
    @abc.abstractmethod
    def name(self):
        """
        Name used to identify the type of call trace e.g. "oomkiller".
        """

    @property
    @abc.abstractmethod
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

    @property
    @abc.abstractmethod
    def heuristics(self):
        """ Return a list of CallTraceHeuristic objects that can be used to
        run checks on any identified call traces. """

    @abc.abstractmethod
    def __len__(self):
        """ Return number of call stacks identified.  """

    @abc.abstractmethod
    def __iter__(self):
        """ Iterate over each call trace found. """


class KernLogBase():

    def __init__(self):
        c = SearchConstraintSearchSince(ts_matcher_cls=CommonTimestampMatcher)
        self.searcher = FileSearcher(constraint=c)
        self.hostnet_helper = HostNetworkingHelper()
        self.cli_helper = CLIHelper()

    @property
    def path(self):
        path = os.path.join(HotSOSConfig.data_root, 'var/log/kern.log')
        if HotSOSConfig.use_all_logs:
            return f"{path}*"

        return path
