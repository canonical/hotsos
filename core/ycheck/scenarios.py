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
from core.ycheck import (
    YDefsLoader,
    YDefsSection,
    ChecksBase,
    YPropertyInput,
    YPropertyExpr,
    YPropertyRequires,
)


class YAMLDefScenarioCheck(YPropertyExpr, YPropertyRequires, YPropertyInput):
    """
    Override grouping used by scenario checks.

    Adds an additional 'meta' override that can be used to provide metadata to
    the check implementation.
    """
    KEYS = [] + YPropertyExpr.KEYS + YPropertyRequires.KEYS + \
        YPropertyInput.KEYS
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
        if self._meta:
            return int(self._meta.period or 0)

        return 0

    @property
    def min(self):
        """
        Minimum search matches required for result to be True (default is 1)
        """
        if self._meta:
            return int(self._meta.min or 1)

        return 1


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
        self.cached_result = None

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
    def _result(self):
        if self.expr:
            s = FileSearcher()
            s.add_search_term(SearchDef(self.expr.value, tag='all'),
                              self.input.path)
            results = s.search()
            if not results:
                log.debug("scenario check %s: False", self.name)
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

    @property
    def result(self):
        log.debug("executing check %s", self.name)
        if self.cached_result is None:
            result = self._result
        else:
            result = self.cached_result

        log.debug("check %s result=%s (cached=%s)", self.name, result,
                  self.cached_result is not None)
        self.cached_result = result
        return result


class ScenarioConclusions(object):
    def __init__(self, name, priority, decision=None, raises=None,
                 checks=None):
        self.name = name
        self.priority = priority
        self.decision = decision
        self.raises = raises
        self.checks = checks
        self.issue_message = None
        self.issue_type = None

    def get_check_result(self, name):
        result = None
        if name in self.checks:
            result = self.checks[name].result
        else:
            raise Exception("conclusion '{}' has unknown check '{}' in "
                            "decision set".format(self.name, name))

        return result

    def _run_conclusion(self):
        if self.decision.is_singleton:
            return self.get_check_result(self.decision.content)
        else:
            for op, checks in self.decision:
                results = [self.get_check_result(c) for c in checks]
                if op == 'and':
                    return all(results)
                elif op == 'or':
                    return any(results)
                else:
                    log.debug("decision has unsupported operator '%s'", op)

        return False

    @property
    def reached(self):
        """ Return true if a conclusion has been reached. """
        result = self._run_conclusion()
        fdict = self.raises.format_dict or {}
        self.issue_message = str(self.raises.message).format(**fdict)
        self.issue_type = self.raises.type
        return result


class Scenario(object):
    def __init__(self, name, checks, conclusions):
        self.name = name
        self._checks = checks
        self._conclusions = conclusions

    @property
    def checks(self):
        section = YDefsSection('checks', self._checks.content)
        _checks = {}
        for c in section.leaf_sections:
            _checks[c.name] = ScenarioCheck(c.name, c.input, c.expr, c.meta,
                                            c.requires)

        return _checks

    @property
    def conclusions(self):
        section = YDefsSection('conclusions', self._conclusions.content)
        _conclusions = {}
        for r in section.leaf_sections:
            priority = r.priority or 1
            _conclusions[r.name] = ScenarioConclusions(r.name,
                                                       int(priority),
                                                       r.decision,
                                                       r.raises, self.checks)

        return _conclusions


class YScenarioChecker(ChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scenarios = []

    def load(self):
        plugin_content = YDefsLoader('scenarios').load_plugin_defs()
        if not plugin_content:
            return

        yscenarios = YDefsSection(constants.PLUGIN_NAME, plugin_content,
                                  extra_overrides=[YAMLDefScenarioCheck])
        if yscenarios.requires and not yscenarios.requires.passes:
            log.debug("plugin '%s' scenarios pre-requisites not met - "
                      "skipping", constants.PLUGIN_NAME)
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
        for scenario in self.scenarios:
            results = {}
            log.debug("running scenario: %s", scenario.name)
            # run all conclusions and use highest priority result(s). One or
            # more conclusions may share the same priority. All conclusions
            # that match and share the same priority will be used.
            for name, conc in scenario.conclusions.items():
                if conc.reached:
                    if conc.priority in results:
                        results[conc.priority].append(conc)
                    else:
                        results[conc.priority] = [conc]

                    log.debug("conclusion reached: %s (priority=%s)", name,
                              conc.priority)

            if results:
                highest = max(results.keys())
                log.debug("selecting highest priority=%s conclusions (%s)",
                          highest, len(results[highest]))
                for conc in results[highest]:
                    issue_utils.add_issue(conc.issue_type(conc.issue_message))
            else:
                log.debug("no conclusions reached")
