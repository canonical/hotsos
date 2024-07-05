from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager, HotSOSScenariosWarning
from hotsos.core.log import log
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YDefsSection,
    YHandlerBase,
)
from hotsos.core.ycheck.engine.properties.common import YDefsContext
from hotsos.core.ycheck.common import GlobalSearcherPreloaderBase
from hotsos.core.ycheck.engine.properties import checks


class ScenariosSearchPreloader(YHandlerBase, GlobalSearcherPreloaderBase):
    """
    Find all scenario checks that have a search property and load their search
    into the global searcher.

    @param global_searcher: GlobalSearcher object
    """

    @staticmethod
    def skip_filtered(path):
        if (HotSOSConfig.scenario_filter and
                path != HotSOSConfig.scenario_filter):
            log.info("skipping scenario %s (filter=%s)", path,
                     HotSOSConfig.scenario_filter)
            return True

        return False

    def preload_searches(self, global_searcher):
        """
        Find all scenario checks that have a search property and load their
        search into the global searcher.
        """
        if global_searcher.is_loaded(self.__class__.__name__):
            raise Exception("scenario searches have already been loaded into "
                            "the global searcher. This operation can only be "
                            "performed once.")

        log.debug("started loading scenario searches into searcher "
                  "(%s)", global_searcher.searcher)
        added = 0
        plugin_defs = YDefsLoader('scenarios').plugin_defs
        root = YDefsSection(HotSOSConfig.plugin_name, plugin_defs or {})
        for prop in root.manager.properties.values():
            if not issubclass(prop[0]['cls'], checks.YPropertyChecks):
                continue

            for item in prop:
                log.debug("looking for searches in %s", item['path'])

                # Walk down to the checks property and keep ref to parent.
                parent = None
                _checks = None
                for branch in item['path'].split('.')[1:]:
                    parent = _checks or root
                    _checks = getattr(root if _checks is None else _checks,
                                      branch)

                # this is needed to resolve search expression references
                _checks.initialise(parent.vars)
                for check in _checks:
                    if check.search is None:
                        continue

                    # Checks can use input outside their scope so we
                    # take that into account here.
                    _input = check.input
                    if _input is None:
                        _input = parent.input

                    log.debug("loading search for check '%s'", check.name)
                    added += 1
                    self._load_item_search(global_searcher, check.search,
                                           _input)

        global_searcher.set_loaded(self.__class__.__name__)
        log.debug("identified a total of %s scenario check searches", added)
        log.debug("finished loading scenario searches into searcher "
                  "(registry now has %s items)", len(global_searcher))

    def run(self):
        # Pre-load all scenario check searches into a global searcher
        self.preload_searches(self.global_searcher)


class Scenario():

    def __init__(self, name, _checks, conclusions):
        log.debug("scenario: %s", name)
        self.name = name
        self._checks = _checks
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

        # It is assumed that the global searcher already exists, is loaded with
        # searches and they have been executed. Unit tests however, should be
        # resetting the registry prior to each run and we will therefore need
        # to load searches each time which is why we do this here. This is
        # therefore not intended to be used outside of a test scenario.
        label = ScenariosSearchPreloader.__name__
        if not self.global_searcher.is_loaded(label):
            log.info("global searcher catalog is empty so launching "
                     "pre-load of scenario searches")
            # NOTE: this is not re-entrant safe and is only ever expected
            #       to be done from a unit test.
            ScenariosSearchPreloader(self.global_searcher).run()

    def load(self):
        plugin_content = YDefsLoader('scenarios').plugin_defs
        if not plugin_content:
            return

        yscenarios = YDefsSection(HotSOSConfig.plugin_name, plugin_content,
                                  context=YDefsContext({'global_searcher':
                                                        self.global_searcher}))
        if (not HotSOSConfig.force_mode and yscenarios.requires and not
                yscenarios.requires.result):
            log.debug("plugin '%s' scenarios pre-requisites not met - "
                      "skipping", HotSOSConfig.plugin_name)
            return

        log.debug("sections=%s, scenarios=%s",
                  len(list(yscenarios.branch_sections)),
                  len(list(yscenarios.leaf_sections)))

        to_skip = set()
        for scenario in yscenarios.leaf_sections:
            fullname = (f"{HotSOSConfig.plugin_name}.{scenario.parent.name}."
                        f"{scenario.name}")
            if ScenariosSearchPreloader.skip_filtered(fullname):
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

            scenario.checks.initialise(scenario.vars)
            scenario.checks.check_context.global_searcher = \
                self.global_searcher
            _scenario = Scenario(scenario.name, scenario.checks,
                                 scenario.conclusions)
            scenario.conclusions.initialise(scenario.vars, _scenario.checks)
            self._scenarios.append(_scenario)

    @property
    def scenarios(self):
        return self._scenarios

    @staticmethod
    def _run_scenario_conclusion(scenario, issue_mgr):
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

    def run(self, load=True):
        if load:
            self.load()

        failed_scenarios = []
        issue_mgr = IssuesManager()
        for scenario in self.scenarios:
            log.debug("running scenario: %s", scenario.name)
            # catch failed scenarios and allow others to run
            try:
                self._run_scenario_conclusion(scenario, issue_mgr)
            # We really do want to catch all here since we don't care why
            # it failed but don't want to fail hard if it does.
            except Exception:  # pylint: disable=W0718
                log.exception("caught exception when running scenario %s:",
                              scenario.name)
                failed_scenarios.append(scenario.name)

        if failed_scenarios:
            msg = ("One or more scenarios failed to run "
                   f"({', '.join(failed_scenarios)}) - run hotsos in "
                   "debug mode (--debug) to get more detail")
            issue_mgr.add(HotSOSScenariosWarning(msg))
