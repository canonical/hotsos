import abc
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    CLIExecError,
    CLIHelper,
    CLIHelperFile,
    HostNetworkingHelper,
)
from hotsos.core.search import (
    CommonTimestampMatcher,
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.log import log

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


class KernLogSource(CLIHelperFile):
    """
    We want to try different sources for kern logs. We implement CLIHelperFile
    so that we can try the systemd journal first and fall back to other paths
    if not successful.
    """
    def __init__(self):
        super().__init__(catch_exceptions=False)
        self.path = None
        self.attempt = 0
        self.fs_paths = ['var/log/kern.log',
                         'sos_commands/logs/journalctl_--no-pager']
        self.fs_paths = [os.path.join(os.path.join(HotSOSConfig.data_root, f))
                         for f in self.fs_paths]

    def __enter__(self):
        if os.path.exists(os.path.join(HotSOSConfig.data_root,
                                       'var/log/journal')):
            try:
                self.path = self.journalctl(opts='-k')
                log.debug("using journal as source of kernlogs")
            except CLIExecError:
                log.info("Failed to get kernlogs from systemd journal. "
                         "Trying fallback sources.")
        else:
            log.info("systemd journal not available. Trying fallback kernlog "
                     "sources.")

        if not self.path:
            for path in self.fs_paths:
                if os.path.exists(path):
                    if path.endswith('kern.log') and HotSOSConfig.use_all_logs:
                        self.path = f"{path}*"
                    else:
                        self.path = path

                    log.debug("using %s as source of kernlogs", self.path)
                    break
            else:
                paths = ', '.join(self.fs_paths)
                log.warning("no kernlog sources found (tried %s and "
                            "journal)", paths)

        return self


class KernLogBase():
    """ Base class for kernlog analysis implementations. """
    def __init__(self):
        self.hostnet_helper = HostNetworkingHelper()
        self.cli_helper = CLIHelper()

    @staticmethod
    def perform_search(searchdefs):
        try:
            constraint = SearchConstraintSearchSince(
                                         ts_matcher_cls=CommonTimestampMatcher)
        except ValueError as exc:
            log.warning("failed to create global search constraint for "
                        "calltrace checker: %s", exc)
            constraint = None

        searcher = FileSearcher(constraint=constraint)
        with KernLogSource() as kls:
            if kls.path is None:
                log.info("no kernlogs found")
                return None

            for sd in searchdefs:
                searcher.add(sd, kls.path)

            return searcher.run()
