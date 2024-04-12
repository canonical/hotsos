from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager, HotSOSScenariosWarning
from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YDefsSection,
    YHandlerBase,
)
from hotsos.core.ycheck.engine.properties.search import (
    CommonTimestampMatcher,
)


class Scenario(object):
    def __init__(self, name, checks, conclusions):
        log.debug("scenario: %s", name)
        self.name = name
        self._checks = checks
        self._conclusions = conclusions

    @property
    def checks(self):
        return {c.name: c for c in self._checks}

    @property
    def conclusions(self):
        return {c.name: c for c in self._conclusions}


class YScenarioChecker(YHandlerBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scenarios = []
        hours = 24
        if HotSOSConfig.use_all_logs:
            hours *= HotSOSConfig.max_logrotate_depth

        constraint = SearchConstraintSearchSince(
                                        ts_matcher_cls=CommonTimestampMatcher,
                                        hours=hours)
        self._searcher = FileSearcher(constraint=constraint)

    @property
    def searcher(self):
        return self._searcher

    def load(self):
        plugin_content = YDefsLoader('scenarios').plugin_defs
        if not plugin_content:
            return

        yscenarios = YDefsSection(HotSOSConfig.plugin_name, plugin_content)
        if (not HotSOSConfig.force_mode and yscenarios.requires and not
                yscenarios.requires.result):
            log.debug("plugin '%s' scenarios pre-requisites not met - "
                      "skipping", HotSOSConfig.plugin_name)
            return

        log.debug("sections=%s, scenarios=%s",
                  len(list(yscenarios.branch_sections)),
                  len(list(yscenarios.leaf_sections)))

        to_skip = set()

        checks = []
        for scenario in yscenarios.leaf_sections:
            fullname = "{}.{}.{}".format(HotSOSConfig.plugin_name,
                                         scenario.parent.name, scenario.name)
            if (HotSOSConfig.scenario_filter and
                    fullname != HotSOSConfig.scenario_filter):
                log.info("skipping scenario %s (filter=%s)", fullname,
                         HotSOSConfig.scenario_filter)
                continue

            # Only register scenarios if requirements are satisfied.
            group_name = scenario.parent.name
            if (not HotSOSConfig.force_mode and
                    (group_name in to_skip or
                        (scenario.requires and not scenario.requires.result))):
                log.debug("%s requirements not met - skipping scenario %s",
                          group_name, scenario.name)
                to_skip.add(group_name)
                continue

            checks.append(scenario.checks)
            scenario.checks.initialise(scenario.vars, scenario.input,
                                       self.searcher, scenario)
            _scenario = Scenario(scenario.name, scenario.checks,
                                 scenario.conclusions)
            scenario.conclusions.initialise(scenario.vars, _scenario.checks)
            self._scenarios.append(_scenario)

        log.debug("executing check searches")
        results = self.searcher.run()
        for check in checks:
            check.check_context.search_results = results

    @property
    def scenarios(self):
        return self._scenarios

    def _run_scenario_conclusion(self, scenario, issue_mgr):
        """ Determine the conclusion of this scenario. """
        results = {}
        # Run conclusions in order of priority. One or more conclusion may
        # share the same priority. If one or more conclusion of the same
        # priority is reached the rest (of lower priority) are ignored.
        last_priority = None
        for conc in sorted(scenario.conclusions.values(), key=lambda _conc:
                           int(_conc.priority or 1), reverse=True):
            priority = int(conc.priority or 1)
            if last_priority is not None:
                if priority < last_priority and last_priority in results:
                    break

            last_priority = priority
            if conc.reached(scenario.checks):
                if priority in results:
                    results[priority].append(conc)
                else:
                    results[priority] = [conc]

                log.debug("conclusion reached: %s (priority=%s)", conc.name,
                          priority)

        if results:
            highest = max(results.keys())
            log.debug("selecting highest priority=%s conclusions (%s)",
                      highest, len(results[highest]))
            for conc in results[highest]:
                issue_mgr.add(conc.issue, context=conc.issue_context)
        else:
            log.debug("no conclusions reached")

    def run(self):
        failed_scenarios = []
        issue_mgr = IssuesManager()
        for scenario in self.scenarios:
            log.debug("running scenario: %s", scenario.name)
            # catch failed scenarios and allow others to run
            try:
                self._run_scenario_conclusion(scenario, issue_mgr)
            except Exception:
                log.exception("caught exception when running scenario %s:",
                              scenario.name)
                failed_scenarios.append(scenario.name)

        if failed_scenarios:
            msg = ("One or more scenarios failed to run ({}) - run hotsos in "
                   "debug mode (--debug) to get more detail".
                   format(', '.join(failed_scenarios)))
            issue_mgr.add(HotSOSScenariosWarning(msg))

    def load_and_run(self):
        self.load()
        return self.run()
