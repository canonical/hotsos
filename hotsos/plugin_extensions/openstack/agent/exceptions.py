import os
import re

from collections import UserDict
from searchkit.utils import MPCache

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.openstack.common import OpenstackChecksBase
from hotsos.core.plugins.openstack.openstack import OPENSTACK_LOGS_TS_EXPR
from hotsos.core.search import (
    FileSearcher,
    SearchDef,
    SearchConstraintSearchSince,
)


class AgentExceptionCheckResults(UserDict):

    def __init__(self, service_obj, results, search_obj):
        self.results = results
        self.service = service_obj
        self.search_obj = search_obj
        self.data = {}
        for name, _results in self.results.items():
            self.data[name] = self._get_agent_results(_results)

    @property
    def agents(self):
        """
        Returns a list of agents for this service that have raised exceptions.
        """
        return list(self.results.keys())

    def _get_agent_results(self, results):
        """ Process exception search results.

        Determine frequency of occurrences. By default they are
        grouped/presented by date but can optionally be grouped by time for
        more granularity.

        Results are expected to have the following groups:
            1: date
            2: time
            3: exception name
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

        for exc_type in exceptions:
            exceptions_sorted = {}
            for k, v in sorted(exceptions[exc_type].items(),
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
            sources = set([r.source_id for r in results])
            files.extend([self.search_obj.resolve_source_id(s)
                          for s in sources])

        return files


class AgentExceptionChecks(OpenstackChecksBase):

    def __init__(self):
        super().__init__()
        self.cache = MPCache('agent_exception_checks', 'openstack_extensions',
                             HotSOSConfig.global_tmp_dir)
        c = SearchConstraintSearchSince(exprs=[OPENSTACK_LOGS_TS_EXPR])
        self.searchobj = FileSearcher(constraint=c)
        # The following are expected to be WARNING
        self._agent_warnings = {
            'nova': ['MessagingTimeout',
                     'DiskNotFound',
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

    def _add_agent_searches(self, project, agent, logs_path, expr_template):
        """
        Add searches we want to apply to agent.

        @param project: OSTProject object
        @param agent: name of agent
        @param logs_path: path to logs we want to search
        @param expr_template: generic search template we use to search all/any
                              exception types in any log file.
        """
        if project.exceptions:
            values = "(?:{})".format('|'.join(project.exceptions))
            expr = expr_template.format(values)
            hint = '( ERROR | Traceback)'
            tag = "{}.{}".format(project.name, agent)

            constraints = True
            # keystone logs have cruft at the start of each line and won't be
            # verifiable with the standard log expr so just disable constraints
            # for these logs for now.
            if project.name == 'keystone':
                constraints = False

            self.searchobj.add(SearchDef(expr, tag=tag, hint=hint),
                               logs_path,
                               allow_global_constraints=constraints)

            warn_exprs = self._agent_warnings.get(project.name, [])
            if warn_exprs:
                values = "(?:{})".format('|'.join(warn_exprs))
                expr = expr_template.format(values)
                self.searchobj.add(SearchDef(expr, tag=tag, hint='WARNING'),
                                   logs_path)

        err_exprs = self._agent_errors.get(project.name, [])
        if err_exprs:
            expr = expr_template.format("(?:{})".
                                        format('|'.join(err_exprs)))
            sd = SearchDef(expr, tag=tag, hint='ERROR')
            self.searchobj.add(sd, logs_path)

    def load(self):
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

    def run(self, search_results):
        """ Process search results to see if we got any hits.

        @param search_results: a searchkit.SearchResultsCollection object.
        @return: a dictionary of services and underlying agents with any
                 exceptions they have raised.
        """
        agent_exceptions = self.cache.get('agent_exceptions') or {}
        if agent_exceptions:
            return agent_exceptions

        log.debug("processing exception search results")
        for name, project in self.ost_projects.all.items():
            if not project.installed:
                continue

            agent_results = {}
            for agent in project.services:
                tag = "{}.{}".format(name, agent)
                results = search_results.find_by_tag(tag)
                if results:
                    agent_results[agent] = results

            if not agent_results:
                continue

            agent_exceptions[name] = AgentExceptionCheckResults(
                                                    self.ost_projects[name],
                                                    agent_results,
                                                    self.searchobj)

        self.cache.set('agent_exceptions', agent_exceptions)
        return agent_exceptions

    def execute(self):
        self.load()
        return self.run(self.searchobj.run())

    def __summary_agent_exceptions(self):
        exc_info = self.execute()
        if exc_info:
            return {agent: dict(info) for agent, info in exc_info.items()}
