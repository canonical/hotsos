import os
import re
from collections import UserDict

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.plugins.openstack.common import OpenstackChecksBase
from hotsos.core.search import (
    FileSearcher,
    SearchDef,
    SearchConstraintSearchSince,
)
from hotsos.core.search import CommonTimestampMatcher


class AgentExceptionCheckResults(UserDict):

    def __init__(self, results, source_id_resolver_callback):
        """
        @param results: list of searchkit.SearchResult objects grouped by
                        agent/log in which they were found.
        @param source_id_resolver_callback: searchkit results contain a
                                            reference to the path that matched
                                            the result and this callback is
                                            called to resolve back to a path.
        """
        super().__init__()
        self.results = results
        self.source_id_resolver_callback = source_id_resolver_callback
        for name, _results in self.results.items():
            self.data[name] = self._tally_results(_results)

    @property
    def agents(self):
        """ Returns a list of agents for that have raised exceptions. """
        return list(self.results.keys())

    @staticmethod
    def _tally_results(results):
        """ Tally search results.

        Returns a dictionary with results grouped/presented by date but
        can optionally be grouped by time for more granularity.

        Each search result is expected to have the following match groups:
            1: date
            2: time
            3: log entry
        """
        exceptions = {}
        for result in results:
            # strip leading/trailing quotes
            exc_name = result.get(3).strip("'")
            if exc_name not in exceptions:
                exceptions[exc_name] = {}

            # results are grouped by date or datetime
            ts_date = result.get(1)
            if HotSOSConfig.event_tally_granularity == 'time':
                # use hours and minutes only
                ts_time = re.compile(r'(\d+:\d+).+').search(result.get(2))[1]
                key = "{}_{}".format(ts_date, ts_time)
            else:
                key = str(ts_date)

            if key not in exceptions[exc_name]:
                exceptions[exc_name][key] = 0

            exceptions[exc_name][key] += 1

        if not exceptions:
            return

        for exc_type, values in exceptions.items():
            exceptions_sorted = {}
            for k, v in sorted(values.items(),
                               key=lambda x: x[0]):
                exceptions_sorted[k] = v

            exceptions[exc_type] = exceptions_sorted

        return exceptions

    @property
    def exceptions_raised(self):
        """ Return a list of exceptions raised by this agent. """
        _exceptions = set()
        for results in self.values():
            for exception in results:
                _exceptions.add(exception)

        return list(_exceptions)

    @property
    def files_w_exceptions(self):
        """ Return a list of files containing exceptions. """
        files = []
        for results in self.results.values():
            sources = set(r.source_id for r in results)
            files.extend([self.source_id_resolver_callback(s)
                          for s in sources])

        return files


class AgentExceptionChecks(OpenstackChecksBase):
    """
    Openstack services/agents will log exceptions using ERROR and
    WARNING log levels depending on who raised them and their
    importance. This class provides a way to identify exceptions in
    logs and provide a per-agent tally by date or time.
    """
    summary_part_index = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agent_results = None
        c = SearchConstraintSearchSince(
                                      ts_matcher_cls=CommonTimestampMatcher)
        self.searchobj = FileSearcher(constraint=c)
        # The following are expected to be logged using WARNING log level.
        self._agent_warnings = {
            'nova': ['MessagingTimeout',
                     'DiskNotFound',
                     r"Timeout waiting for \[\('\S+',",
                     ],
            'neutron': [r'OVS is dead',
                        r'MessagingTimeout',
                        ]
        }

        # The following are expected to be ERROR. This is typically used to
        # catch events that are not logged as an exception with the usual
        # Traceback format.
        self._agent_errors = {
            'neutron': [r'RuntimeError'],
            'keystone': [r'\([a-zA-Z\.]+\)']
        }

    def _add_agent_searches(self, project, agent_name, logs_path,
                            expr_template):
        """
        Add searches we want to apply to agent.

        @param project: OSTProject object
        @param agent_name: name of agent
        @param logs_path: path to logs we want to search
        @param expr_template: generic search template we use to search all/any
                              exception types in any log file.
        """
        constraints = True
        # keystone logs have cruft at the start of each line and won't be
        # verifiable with the standard log expr so just disable constraints
        # for these logs for now.
        if project.name == 'keystone':
            constraints = False

        tag = "{}.{}".format(project.name, agent_name)
        if project.exceptions:
            exc_names = "(?:{})".format('|'.join(project.exceptions))
            expr = expr_template.format(exc_names)
            self.searchobj.add(SearchDef(expr, tag=tag + '.error',
                                         hint='( ERROR | Traceback)'),
                               logs_path,
                               allow_global_constraints=constraints)

        warn_exprs = self._agent_warnings.get(project.name, [])
        if warn_exprs:
            values = "(?:{})".format('|'.join(warn_exprs))
            expr = expr_template.format(values)
            self.searchobj.add(SearchDef(expr, tag=tag + '.warning',
                                         hint='WARNING'), logs_path,
                               allow_global_constraints=constraints)

        err_exprs = self._agent_errors.get(project.name, [])
        if err_exprs:
            values = "(?:{})".format('|'.join(err_exprs))
            expr = expr_template.format(values)
            sd = SearchDef(expr, tag=tag + '.error', hint='ERROR')
            self.searchobj.add(sd, logs_path,
                               allow_global_constraints=constraints)

    def _load(self):
        """Register searches for exceptions as well as any other type of issue
        we might want to catch like warnings etc which may not be errors or
        exceptions.
        """
        log.debug("loading exception search defs")
        for project in self.ost_projects.all.values():
            if not project.installed:
                log.debug("%s is not installed - excluding from exception "
                          "checks", project.name)
                continue

            log.debug("%s is installed so adding to searches", project.name)

            wsgi_prefix = ''
            if 'apache2' in project.services:
                # NOTE: services running under apache may have their logs (e.g.
                # barbican-api.log) prepended with apache/mod_wsgi info so do
                # this way to account for both. If present, the prefix will be
                # ignored and not count towards the result.
                wsgi_prefix = r'\[[\w :\.]+\].+\]\s+'

            keystone_prefix = ''
            if project.name == 'keystone':
                # keystone logs contain the (module_name): at the beginning of
                # the line.
                keystone_prefix = r'\(\S+\):\s+'

            prefix_match = ''
            if all([wsgi_prefix, keystone_prefix]):
                prefix_match = r'(?:{}|{})?'.format(wsgi_prefix,
                                                    keystone_prefix)
            elif any([wsgi_prefix, keystone_prefix]):
                prefix_match = (r'(?:{})?'.
                                format(wsgi_prefix or keystone_prefix))

            # Sometimes the exception is printed with just the class name
            # and sometimes it is printed with a full import path e.g.
            # MyExc or somemod.MyExc so we need to account for both.
            exc_obj_full_path_match = r'(?:\S+\.)?'
            expr_template = (r"^{}([0-9\-]+) (\S+) .+\S+\s({}{{}})[\s:\.]".
                             format(prefix_match, exc_obj_full_path_match))

            # NOTE: don't check exceptions for deprecated services
            for agent, log_paths in project.log_paths(
                    include_deprecated_services=False):
                for path in log_paths:
                    path = os.path.join(HotSOSConfig.data_root, path)
                    if HotSOSConfig.use_all_logs:
                        path = "{}*".format(path)

                    self._add_agent_searches(project, agent, path,
                                             expr_template)

    def _run(self, search_results):
        """ Process search results to see if we got any hits.

        @param search_results: a searchkit.SearchResultsCollection object.
        @return: a dictionary of services and underlying agents with any
                 exceptions they have raised.
        """
        log.debug("processing exception search results")
        agent_exceptions = {}
        for name, project in self.ost_projects.all.items():
            if not project.installed:
                continue

            for log_level in ['warning', 'error']:
                agent_results = {}
                for agent in project.services:
                    tag = "{}.{}".format(name, agent)
                    results = search_results.find_by_tag(tag + '.' + log_level)
                    if results:
                        agent_results[agent] = results

                if not agent_results:
                    continue

                if log_level not in agent_exceptions:
                    agent_exceptions[log_level] = {}

                callback = self.searchobj.catalog.source_id_to_path
                _results = AgentExceptionCheckResults(agent_results, callback)
                agent_exceptions[log_level][name] = _results

        return agent_exceptions

    @property
    def agent_results(self):
        if self._agent_results is not None:
            return self._agent_results

        self._load()
        self._agent_results = self._run(self.searchobj.run())
        return self._agent_results

    def __200_summary_agent_exceptions(self):
        """
        Only ERROR level exceptions
        """
        if self.agent_results and 'error' in self.agent_results:
            _exc_info = {}
            for svc, results in self.agent_results['error'].items():
                _exc_info[svc] = dict(results)

            return {agent: dict(info) for agent, info in _exc_info.items()}

    def __201_summary_agent_warnings(self):
        """
        Only WARNING level exceptions
        """
        if self.agent_results and 'warning' in self.agent_results:
            _exc_info = {}
            for svc, results in self.agent_results['warning'].items():
                _exc_info[svc] = dict(results)

            return {agent: dict(info) for agent, info in _exc_info.items()}
