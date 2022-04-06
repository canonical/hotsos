from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
from hotsos.core.log import log
from hotsos.core.ycheck import (
    YDefsLoader,
    YDefsSection,
    ChecksBase,
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


class YScenarioChecker(ChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scenarios = []

    def load(self):
        plugin_content = YDefsLoader('scenarios').load_plugin_defs()
        if not plugin_content:
            return

        yscenarios = YDefsSection(HotSOSConfig.PLUGIN_NAME, plugin_content)
        if yscenarios.requires and not yscenarios.requires.passes:
            log.debug("plugin '%s' scenarios pre-requisites not met - "
                      "skipping", HotSOSConfig.PLUGIN_NAME)
            return

        log.debug("sections=%s, scenarios=%s",
                  len(yscenarios.branch_sections),
                  len(yscenarios.leaf_sections))

        for scenario in yscenarios.leaf_sections:
            if scenario.requires:
                requires_passes = scenario.requires.passes
            else:
                requires_passes = True

            if requires_passes:
                self._scenarios.append(Scenario(scenario.name,
                                                scenario.checks,
                                                scenario.conclusions))

    @property
    def scenarios(self):
        return self._scenarios

    def run(self):
        mgr = IssuesManager()
        for scenario in self.scenarios:
            results = {}
            log.debug("running scenario: %s", scenario.name)
            # run all conclusions and use highest priority result(s). One or
            # more conclusions may share the same priority. All conclusions
            # that match and share the same priority will be used.
            for name, conc in scenario.conclusions.items():
                if conc.reached(scenario.checks):
                    if conc.priority:
                        priority = conc.priority.value
                    else:
                        priority = 1

                    if priority in results:
                        results[priority].append(conc)
                    else:
                        results[priority] = [conc]

                    log.debug("conclusion reached: %s (priority=%s)", name,
                              priority)

            if results:
                highest = max(results.keys())
                log.debug("selecting highest priority=%s conclusions (%s)",
                          highest, len(results[highest]))
                for conc in results[highest]:
                    mgr.add(conc.issue, context=conc.context)
            else:
                log.debug("no conclusions reached")
