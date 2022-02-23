import os
import re

from core.log import log
from core import constants
from core.searchtools import SearchDef
from core.plugins.openstack import (
    OpenstackEventChecksBase,
    AGENT_ERROR_KEY_BY_TIME,
)
from core.searchtools import FileSearcher

YAML_PRIORITY = 7


class AgentExceptionChecks(OpenstackEventChecksBase):

    def __init__(self):
        # NOTE: we are OpenstackEventChecksBase to get the call structure but
        # we dont currently use yaml to define out searches.
        super().__init__(yaml_defs_group='agent-exceptions',
                         searchobj=FileSearcher())
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
        # catch events that are not defined as an exception.
        self._agent_errors = {
            'neutron': [r'RuntimeError']
            }

    def _add_agent_searches(self, project, agent, data_source, expr_template):
        if project.exceptions:
            values = "(?:{})".format('|'.join(project.exceptions))
            expr = expr_template.format(values)
            hint = '( ERROR | Traceback)'
            tag = "{}.{}".format(project.name, agent)
            self.searchobj.add_search_term(SearchDef(expr, tag=tag, hint=hint),
                                           data_source)

            warn_exprs = self._agent_warnings.get(project.name, [])
            if warn_exprs:
                values = "(?:{})".format('|'.join(warn_exprs))
                expr = expr_template.format(values)
                self.searchobj.add_search_term(SearchDef(expr, tag=tag,
                                                         hint='WARNING'),
                                               data_source)

        err_exprs = self._agent_errors.get(project.name, [])
        if err_exprs:
            expr = expr_template.format("(?:{})".
                                        format('|'.join(err_exprs)))
            sd = SearchDef(expr, tag=tag, hint='ERROR')
            self.searchobj.add_search_term(sd, data_source)

    def load(self):
        """Register searches for exceptions as well as any other type of issue
        we might want to catch like warnings etc which may not be errors or
        exceptions.
        """
        for project in self.ost_projects.all.values():
            if not project.installed:
                log.debug("%s is not installed - excluding from exception "
                          "checks", project.name)
                continue

            # NOTE: services running under apache may have their logs (e.g.
            # barbican-api.log) prepended with apache/mod_wsgi info so do this
            # way to account for both. If present, the prefix will be ignored
            # and not count towards the result.
            wsgi_prefix = r'\[[\w :\.]+\].+\]\s+'
            # keystone logs contain the (module_name): at the beginning of the
            # line.
            keystone_prefix = r'\(\S+\):\s+'
            prefix_match = r'(?:{}|{})?'.format(wsgi_prefix, keystone_prefix)

            # Sometimes the exception is printed with just the class name
            # and sometimes it is printed with a full import path e.g.
            # MyExc or somemod.MyExc so we need to account for both.
            exc_obj_full_path_match = r'(?:\S+\.)?'
            expr_template = (r"^{}([0-9\-]+) (\S+) .+\S+\s({}{{}})[\s:\.]".
                             format(prefix_match, exc_obj_full_path_match))

            for agent, log_paths in project.log_paths:
                for path in log_paths:
                    path = os.path.join(constants.DATA_ROOT, path)
                    if constants.USE_ALL_LOGS:
                        path = "{}*".format(path)

                    self._add_agent_searches(project, agent, path,
                                             expr_template)

    def get_exceptions_results(self, results):
        """ Process exception search results.

        Determine frequency of occurrences. By default they are
        grouped/presented by date but can optionally be grouped by time for
        more granularity.
        """
        agent_exceptions = {}
        for result in results:
            # strip leading/trailing quotes
            exc_tag = result.get(3).strip("'")
            if exc_tag not in agent_exceptions:
                agent_exceptions[exc_tag] = {}

            ts_date = result.get(1)
            if AGENT_ERROR_KEY_BY_TIME:
                # use hours and minutes only
                ts_time = re.compile(r'(\d+:\d+).+').search(result.get(2))[1]
                key = "{}_{}".format(ts_date, ts_time)
            else:
                key = str(ts_date)

            if key not in agent_exceptions[exc_tag]:
                agent_exceptions[exc_tag][key] = 0

            agent_exceptions[exc_tag][key] += 1

        if not agent_exceptions:
            return

        for exc_type in agent_exceptions:
            agent_exceptions_sorted = {}
            for k, v in sorted(agent_exceptions[exc_type].items(),
                               key=lambda x: x[0]):
                agent_exceptions_sorted[k] = v

            agent_exceptions[exc_type] = agent_exceptions_sorted

        return agent_exceptions

    def run(self, results):
        """Process search results to see if we got any hits."""
        issues = {}
        for name, info in self.ost_projects.all.items():
            for agent in info.services:
                tag = "{}.{}".format(name, agent)
                _results = results.find_by_tag(tag)
                ret = self.get_exceptions_results(_results)
                if ret:
                    if name not in issues:
                        issues[name] = {}

                    issues[name][agent] = ret

        if issues:
            self._output['agent-exceptions'] = issues
