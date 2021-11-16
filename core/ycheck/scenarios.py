from datetime import (
    datetime,
    timedelta,
)

from core import constants
from core.issues import issue_utils
from core.searchtools import (
    FileSearcher,
    SearchDef,
)
from core.log import log
from core.ystruct import YAMLDefSection
from core.ycheck import (
    YDefsLoader,
    AutoChecksBase,
    YAMLDefExpr,
    YAMLDefRequires,
    YAMLDefInput,
    YAMLDefIssue,
    YAMLDefMessage,
    YAMLDefDecision,
    YAMLDefChecks,
    YAMLDefConclusions,
    YAMLDefPriority,
)


class YAMLDefScenarioCheck(YAMLDefExpr, YAMLDefRequires, YAMLDefInput):
    """
    Override grouping used by scenario checks.

    Adds an additional 'meta' override that can be used to provide metadata to
    the check implementation.
    """
    KEYS = [] + YAMLDefExpr.KEYS + YAMLDefRequires.KEYS + YAMLDefInput.KEYS
    KEYS.append('meta')

    def __getattr__(self, name):
        if self._override_name == 'meta':
            return self.content.get(name)
        else:
            return super().__getattr__(name)


class ScenarioCheckMeta(object):

    def __init__(self, meta):
        self._meta = meta or {}

    @property
    def period(self):
        """
        If min is provided this is used to determine the period within which
        min applies. If period is unset, the period is infinite i.e. across all
        available data.

        Supported values:
          <int> hours

        """
        return self._meta.period

    @property
    def min(self):
        """
        Minimum search matches required for result to be True (default is 1)
        """
        return int(self._meta.min or 1)


class ScenarioCheck(object):
    """
    See YAMLDefScenarioCheck for overrides used with this class.

    A scenario is defined as requiring one (and only one) of the following:
        * a search expression to match against an input (file or command).
        * a property to match a given value

    See ScenarioCheckMeta for optional metadata.
    """
    def __init__(self, name, input=None, expr=None, meta=None, requires=None):
        self.name = name
        self.input = input
        self.expr = expr
        self.meta = ScenarioCheckMeta(meta)
        self.requires = requires

    @classmethod
    def get_datetime_from_result(cls, result):
        ts = "{} {}".format(result.get(1), result.get(2))
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")

    @classmethod
    def filter_by_period(cls, results, period, min_results):
        _results = []
        for r in results:
            ts = cls.get_datetime_from_result(r)
            _results.append((ts, r))

        results = []
        last = None
        prev = None
        count = 0

        for r in sorted(_results, key=lambda i: i[0], reverse=True):
            if last is None:
                last = r[0]
            elif r[0] < last - timedelta(hours=period):
                last = prev
                prev = None
                # pop first element since it is now invalidated
                count -= 1
                results = results[1:]
            elif prev is None:
                prev = r[0]

            results.append(r)
            count += 1
            if count >= min_results:
                # we already have enough results so return
                break

        if len(results) < min_results:
            return []

        return [r[1] for r in results]

    @property
    def result(self):
        if self.expr:
            s = FileSearcher()
            s.add_search_term(SearchDef(self.expr.value, tag='all'),
                              self.input.path)
            results = s.search()
            if not results:
                log.debug("scenario check %s: False")
                return False

            results = results.find_by_tag('all')
            if self.meta.min:
                if self.meta.period:
                    count = len(self.filter_by_period(results,
                                                      self.meta.period,
                                                      self.meta.min))
                else:
                    count = len(results)

                if count >= self.meta.min:
                    return True
                else:
                    log.debug("scenario check %s: not enough matches (%s) to "
                              "satisfy min of %s", self.name, count,
                              self.meta.min)
                    return False
            else:
                return len(results) > 0

        elif self.requires:
            return self.requires.passes
        else:
            raise Exception("unknown scenario check type")


class ScenarioConclusions(object):
    def __init__(self, priority, decision=None, issue=None, checks=None):
        self.priority = priority
        self.decision = decision
        self.issue = issue
        self.checks = checks
        self.issue_message = None
        self.issue_type = None

    def get_check_result(self, name):
        result = None
        if name in self.checks:
            result = self.checks[name].result

        return result

    def _run_conclusion(self):
        if self.decision.is_singleton:
            return self.get_check_result(self.decision.content)
        else:
            for _bool, checks in self.decision:
                results = [self.get_check_result(c) for c in checks]
                if _bool == 'and':
                    return all(results)
                elif _bool == 'or':
                    return any(results)
                else:
                    log.debug("unsupported boolean decsion '%s'", _bool)

        return False

    @property
    def reached(self):
        """ Return true if a conclusion has been reached. """
        result = self._run_conclusion()
        fdict = self.issue.format_dict or {}
        self.issue_message = str(self.issue.message).format(**fdict)
        self.issue_type = self.issue.type
        return result


class Scenario(object):
    def __init__(self, name, checks, conclusions):
        self.name = name
        self._checks = checks
        self._conclusions = conclusions

    @property
    def checks(self):
        overrides = [YAMLDefScenarioCheck]
        section = YAMLDefSection('checks',
                                 self._checks.content,
                                 override_handlers=overrides)
        _checks = {}
        for c in section.leaf_sections:
            _checks[c.name] = ScenarioCheck(c.name, c.input, c.expr, c.meta,
                                            c.requires)

        return _checks

    @property
    def conclusions(self):
        overrides = [YAMLDefDecision, YAMLDefIssue]
        section = YAMLDefSection('conclusions', self._conclusions.content,
                                 override_handlers=overrides)
        _conclusions = {}
        for r in section.leaf_sections:
            _conclusions[r.name] = ScenarioConclusions(int(r.priority),
                                                       r.decision,
                                                       r.issue, self.checks)

        return _conclusions


class YScenarioChecker(AutoChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scenarios = []

    def load(self):
        plugin = YDefsLoader('scenarios').load_plugin_defs()
        if not plugin:
            return

        overrides = [YAMLDefMessage, YAMLDefDecision, YAMLDefChecks,
                     YAMLDefConclusions, YAMLDefPriority, YAMLDefScenarioCheck]
        # TODO: need a better way to provide this instance to the input
        #       override.
        YAMLDefScenarioCheck.EVENT_CHECK_OBJ = self
        yscenarios = YAMLDefSection(constants.PLUGIN_NAME, plugin,
                                    override_handlers=overrides)

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
        for scenario in self.scenarios:
            result = None
            log.debug("running scenario: %s", scenario.name)
            # run all conclusions and use highest priority result
            for name, conc in scenario.conclusions.items():
                if conc.reached:
                    if not result:
                        result = conc
                    elif conc.priority > result.priority:
                        result = conc

                    log.debug("conclusion is: %s (priority=%s)", name,
                              result.priority)

            if result:
                issue_utils.add_issue(result.issue_type(result.issue_message))
