import os
import re

from core import constants
from core.searchtools import SearchDef
from core.plugins.openstack import (
    OpenstackEventChecksBase,
    OPENSTACK_AGENT_ERROR_KEY_BY_TIME,
    SERVICE_RESOURCES,
)
from core.plugins.openstack.exceptions import (
    BARBICAN_EXCEPTIONS,
    CASTELLAN_EXCEPTIONS,
    CINDER_EXCEPTIONS,
    KEYSTONE_EXCEPTIONS,
    MANILA_EXCEPTIONS,
    PYTHON_LIBVIRT_EXCEPTIONS,
    NOVA_EXCEPTIONS,
    NEUTRON_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OVSDBAPP_EXCEPTIONS,
)

YAML_PRIORITY = 7


class AgentExceptionChecks(OpenstackEventChecksBase):

    def __init__(self):
        # NOTE: we are OpenstackEventChecksBase to get the call structure but
        # we dont currently use yaml to define out searches.
        super().__init__(yaml_defs_group='agent-exceptions')
        self._exception_exprs = {}

        # The following are expected to be ERROR or Traceback
        self._agent_exceptions = {'barbican': BARBICAN_EXCEPTIONS,
                                  'cinder': CINDER_EXCEPTIONS,
                                  'keystone': KEYSTONE_EXCEPTIONS,
                                  'manila': MANILA_EXCEPTIONS,
                                  'neutron': NEUTRON_EXCEPTIONS,
                                  'nova': NOVA_EXCEPTIONS +
                                  PYTHON_LIBVIRT_EXCEPTIONS,
                                  'octavia': OCTAVIA_EXCEPTIONS,
                                  }

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

    def _prepare_exception_expressions(self):
        for svc in SERVICE_RESOURCES:
            self._exception_exprs[svc] = []
            self._exception_exprs[svc] += self._agent_exceptions.get(svc, [])
            svc_base_exceptions = SERVICE_RESOURCES[svc]['exceptions_base']
            self._exception_exprs[svc] += svc_base_exceptions

            # Add service dependency/lib/client exceptions
            if svc == 'cinder' or svc == 'barbican':
                for exc in CASTELLAN_EXCEPTIONS:
                    self._exception_exprs[svc].append(exc)
            elif svc == 'neutron':
                for exc in OVSDBAPP_EXCEPTIONS:
                    self._exception_exprs[svc].append(exc)

    def _add_exception_searches(self):
        for svc, exc_exprs in self._exception_exprs.items():
            logpath = SERVICE_RESOURCES[svc]['logs']
            data_source_template = os.path.join(constants.DATA_ROOT,
                                                logpath, '{}.log')
            if constants.USE_ALL_LOGS:
                data_source_template = "{}*".format(data_source_template)

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

            for agent in SERVICE_RESOURCES[svc]['daemons']:
                data_source = data_source_template.format(agent)
                expr = expr_template.format("(?:{})".
                                            format('|'.join(exc_exprs)))
                hint = '( ERROR | Traceback)'
                sd = SearchDef(expr, tag=agent, hint=hint)
                self.searchobj.add_search_term(sd, data_source)

                warn_exprs = self._agent_warnings.get(svc, [])
                if warn_exprs:
                    expr = expr_template.format("(?:{})".
                                                format('|'.join(warn_exprs)))
                    sd = SearchDef(expr, tag=agent, hint='WARNING')
                    self.searchobj.add_search_term(sd, data_source)

                err_exprs = self._agent_errors.get(svc, [])
                if err_exprs:
                    expr = expr_template.format("(?:{})".
                                                format('|'.join(err_exprs)))
                    sd = SearchDef(expr, tag=agent, hint='ERROR')
                    self.searchobj.add_search_term(sd, data_source)

    def register_search_terms(self):
        """Register searches for exceptions as well as any other type of issue
        we might want to catch like warning etc which may not be errors or
        exceptions.
        """
        self._prepare_exception_expressions()
        self._add_exception_searches()

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
            if OPENSTACK_AGENT_ERROR_KEY_BY_TIME:
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

    def process_results(self, results):
        """Process search results to see if we got any hits."""
        issues = {}
        for service in SERVICE_RESOURCES:
            for agent in SERVICE_RESOURCES[service]['daemons']:
                _results = results.find_by_tag(agent)
                ret = self.get_exceptions_results(_results)
                if ret:
                    if service not in issues:
                        issues[service] = {}

                    issues[service][agent] = ret

        if issues:
            self._output['agent-exceptions'] = issues
