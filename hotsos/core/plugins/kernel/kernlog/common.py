import abc
import os

from searchkit.constraints import TimestampMatcherBase
from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, HostNetworkingHelper
from hotsos.core.search import FileSearcher, SearchConstraintSearchSince

KERNLOG_TS = r'\[\s*\d+\.\d+\]'
KERNLOG_PREFIX = (r'(?:\S+\s+\d+\s+[\d:]+\s+\S+\s+\S+:\s+)?{}'.
                  format(KERNLOG_TS))


class KernLogTimestampMatcher(TimestampMatcherBase):
    """
    kern.log has a slightly esoteric timestamp format so we have to do a little
    juggling to get it into a standard format that can be used with search
    constraints.

    NOTE: remember to update
          hotsos.core.ycheck.engine.properties.search.CommonTimestampMatcher
          if necessary.
    """
    MONTH_MAP = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
                 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
                 'nov': 11, 'dec': 12}

    @property
    def year(self):
        """ Use current year as it is not normally included in the logs """
        return CLIHelper().date(format='+%Y')

    @property
    def month(self):
        _month = self.result.group('month').lower()
        try:
            return self.MONTH_MAP[_month[:3]]
        except KeyError:
            log.exception("could not establish month integer from '%s'",
                          _month)

    @property
    def patterns(self):
        return [r'^(?P<month>\w{3,5})\s+(?P<day>\d{1,2})\s+'
                r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})']


class CallTraceHeuristicBase(object):
    """ Defines a common interface for heuristics implementations. """

    @abc.abstractmethod
    def __call__(self):
        """ Ensure callable to get results. """


class CallTraceStateBase(object):
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


class KernLogBase(object):

    def __init__(self):
        c = SearchConstraintSearchSince(ts_matcher_cls=KernLogTimestampMatcher)
        self.searcher = FileSearcher(constraint=c)
        self.hostnet_helper = HostNetworkingHelper()
        self.cli_helper = CLIHelper()

    @property
    def path(self):
        path = os.path.join(HotSOSConfig.data_root, 'var/log/kern.log')
        if HotSOSConfig.use_all_logs:
            return "{}*".format(path)

        return path
