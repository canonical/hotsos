import os
import re

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.openstack.common import OpenstackChecksBase
from hotsos.core.plugins.openstack.openstack import OPENSTACK_LOGS_TS_EXPR
from hotsos.core.search import FileSearcher, SearchDef
from hotsos.core.search.constraints import SearchConstraintSearchSince


class AgentExceptionChecks(OpenstackChecksBase):

    def __init__(self):
        super().__init__()
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

    def _add_agent_searches(self, project, agent, data_source, expr_template):
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

            self.searchobj.add_search_term(
                                        SearchDef(expr, tag=tag, hint=hint),
                                        data_source,
                                        allow_global_constraints=constraints)

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
            if HotSOSConfig.agent_error_key_by_time:
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
        log.debug("processing exception search results")
        _final_results = {}
        for name, project in self.ost_projects.all.items():
            if not project.installed:
                continue

            for agent in project.services:
                tag = "{}.{}".format(name, agent)
                _results = results.find_by_tag(tag)
                log.debug("processing project=%s agent=%s (results=%s)", name,
                          agent, len(_results))
                ret = self.get_exceptions_results(_results)
                if ret:
                    if name not in _final_results:
                        _final_results[name] = {}

                    _final_results[name][agent] = ret

        return _final_results

    def __summary_agent_exceptions(self):
        self.load()
        ret = self.run(self.searchobj.search())
        if ret:
            return ret
