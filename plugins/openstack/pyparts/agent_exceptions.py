import os
import re

from common import constants
from common.searchtools import SearchDef
from common.plugins.openstack import (
    OpenstackEventChecksBase,
    OPENSTACK_AGENT_ERROR_KEY_BY_TIME as AGENT_ERROR_KEY_BY_TIME,
    SERVICE_RESOURCES,
)
from common.plugins.openstack.exceptions import (
    BARBICAN_EXCEPTIONS,
    CASTELLAN_EXCEPTIONS,
    CINDER_EXCEPTIONS,
    MANILA_EXCEPTIONS,
    NOVA_EXCEPTIONS,
    NEUTRON_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OVSDBAPP_EXCEPTIONS,
)

AGENT_DEP_EXCEPTION_EXPR_TEMPLATE = r" (\S*\.?{}):"
YAML_PRIORITY = 7


class AgentExceptionChecks(OpenstackEventChecksBase):

    def __init__(self):
        # NOTE: we are OpenstackEventChecksBase to get the call structure but
        # we dont currently use yaml to define out searches.
        super().__init__(yaml_defs_group='agent-exceptions')
        self._exception_exprs = {}
        self._agent_exceptions = {"barbican": BARBICAN_EXCEPTIONS,
                                  "cinder": CINDER_EXCEPTIONS,
                                  "manila": MANILA_EXCEPTIONS,
                                  "neutron": NEUTRON_EXCEPTIONS,
                                  "nova": NOVA_EXCEPTIONS,
                                  "octavia": OCTAVIA_EXCEPTIONS,
                                  }
        # The following are WARNINGs
        self._agent_warnings = {
            "nova": [r"(MessagingTimeout)"],
            "neutron": [r"(OVS is dead).", r"(MessagingTimeout)"]
            }

        # The following are ERRORs
        self._agent_errors = {
            "neutron": [r"(RuntimeError):"]
            }

    def _prepare_exception_expressions(self):
        for svc in SERVICE_RESOURCES:
            svc_info = SERVICE_RESOURCES[svc]
            a_excs = []
            for e in self._agent_exceptions.get(svc, []):
                # sometimes the exception is printed with just the class name
                # and sometimes it is printed with a full parent module
                # path e.g. BigExc or foo.bar.BigExc so we need to account for
                # both.
                a_excs.append((r" ((?:\S+\.)?{}):".format(e)))

            self._exception_exprs[svc] = []
            self._exception_exprs[svc] += svc_info["exceptions_base"]
            self._exception_exprs[svc] += a_excs

            # Add service dependecy/lib/client exceptions
            if svc == "cinder" or svc == "barbican":
                # This is a client/interface implemenation not a service so we
                # add it to services that implement it. We print the long
                # form of the exception to indicate it is a non-native
                # exception.
                for exc in CASTELLAN_EXCEPTIONS:
                    expr = AGENT_DEP_EXCEPTION_EXPR_TEMPLATE.format(exc)
                    self._exception_exprs[svc].append(expr)
            elif svc == "neutron":
                for exc in OVSDBAPP_EXCEPTIONS:
                    expr = AGENT_DEP_EXCEPTION_EXPR_TEMPLATE.format(exc)
                    self._exception_exprs[svc].append(expr)

    def _add_exception_searches(self):
        for svc, exprs in self._exception_exprs.items():
            logpath = SERVICE_RESOURCES[svc]["logs"]
            data_source_template = os.path.join(constants.DATA_ROOT,
                                                logpath, '{}.log')
            if constants.USE_ALL_LOGS:
                data_source_template = "{}*".format(data_source_template)

            # NOTE: services running under apache have their logs
            # prepending with a load of apache/mod_wsgi info so we have
            # to do this way to account for both. We ignore the apache
            # prefix and it will not count towards the result.
            expr_template = (r"^(?:\[[\w :\.]+\].+\]\s+)?([0-9\-]+) (\S+) "
                             ".+{}.*")

            for agent in SERVICE_RESOURCES[svc]["daemons"]:
                data_source = data_source_template.format(agent)
                for subexpr in exprs:
                    expr = expr_template.format(subexpr)
                    hint = "( ERROR | Traceback)"
                    sd = SearchDef(expr, tag=agent, hint=hint)
                    self.searchobj.add_search_term(sd, data_source)

                for subexpr in self._agent_warnings.get(svc, []):
                    expr = expr_template.format(subexpr)
                    sd = SearchDef(expr, tag=agent, hint="WARNING")
                    self.searchobj.add_search_term(sd, data_source)

                for subexpr in self._agent_errors.get(svc, []):
                    expr = expr_template.format(subexpr)
                    sd = SearchDef(expr, tag=agent, hint="ERROR")
                    self.searchobj.add_search_term(sd, data_source)

    def register_search_terms(self):
        """Register searches for exceptions as well as any other type of issue
        we might want to catch like warning etc which may not be errors or
        exceptions.
        """
        self._prepare_exception_expressions()
        self._add_exception_searches()

    def get_exceptions_results(self, results, include_time_in_key=False):
        """Search results and determine frequency of occurrences of the given
        exception types.

        @param include_time_in_key: (bool) whether to include time of exception
                                    in output. Default is to only show date.
        """
        agent_exceptions = {}
        for result in results:
            exc_tag = result.get(3)
            if exc_tag not in agent_exceptions:
                agent_exceptions[exc_tag] = {}

            if include_time_in_key:
                # use hours and minutes only
                time = re.compile("([0-9]+:[0-9]+).+").search(result.get(2))[1]
                key = "{}_{}".format(result.get(1), time)
            else:
                key = str(result.get(1))

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
            for agent in SERVICE_RESOURCES[service]["daemons"]:
                _results = results.find_by_tag(agent)
                ret = self.get_exceptions_results(_results,
                                                  AGENT_ERROR_KEY_BY_TIME)
                if ret:
                    if service not in issues:
                        issues[service] = {}

                    issues[service][agent] = ret

        if issues:
            self._output["agent-exceptions"] = issues
