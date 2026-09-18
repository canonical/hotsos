import os
import re
import json
from unittest import TestCase
import logging
import sys

import yaml
from tests.unit import utils
from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.engine.common import YDefsLoader


# Recognised leading timestamp capture patterns, matched against the regex
# source of a search expression (after stripping an optional '^' anchor). Each
# alternative captures the date (and usually time) at the start of the line as
# the first result group(s). Examples of expressions each alternative accepts:
#   ([\d-]+)T([\d:]+)...                 journalctl ISO 8601
#   ([\d-]+) ([\d:]+)...                 file log, space separated
#   ([\d-]+ [\d:]+.\d{3})...             combined date+time single group
#   (\d{4}-\d{2}-\d{2}) ...              explicit year
#   (\w{3,5}\s+\d{1,2}\s+[\d:]+) ...     syslog/kern.log style
#   (\S+) (\S+) ...                      loose date/time tokens
LEADING_TIMESTAMP_RE = re.compile(
    r"(?:"
    r"\(\[\\d-\]\+ \[\\d:\]"       # ([\d-]+ [\d:]   (combined date+time group)
    r"|\(\[\\d-\]\+\)"             # ([\d-]+)
    r"|\(\[\\d/-\]\+\)"            # ([\d/-]+)
    r"|\(\\d\{4\}"                 # (\d{4}
    r"|\(\\w\{\d+,\d*\}\\s"        # (\w{3,5}\s      (syslog month)
    r"|\(\\S\+\)[ T]\("            # (\S+) (         (loose token then group)
    r")"
)


class SearchExpressionValidator:
    """
    Evaluate search expressions that use constraints to make sure they are
    matching the required timestamps.
    """

    @staticmethod
    def is_compliant(pattern):
        """Return True if the regex source starts with a leading timestamp
        capture.
        """
        if not isinstance(pattern, str):
            return False
        candidate = pattern[1:] if pattern.startswith("^") else pattern
        return bool(LEADING_TIMESTAMP_RE.match(candidate))

    def resolve_expr(self, expr, variables):
        """Resolve a check 'expr' value into a flat list of pattern strings.

        Handles list expressions (boolean searches) and simple '$name'
        references
        into the scenario's file level 'vars:' block. Values that cannot be
        resolved are returned as-is so the caller can report them.
        """
        resolved = []
        if isinstance(expr, list):
            for item in expr:
                resolved.extend(self.resolve_expr(item, variables))
        elif isinstance(expr, str):
            if expr.startswith("$"):
                value = variables.get(expr[1:])
                if value is None:
                    # unresolved, keep literal for reporting
                    resolved.append(expr)
                else:
                    resolved.extend(self.resolve_expr(value, variables))
            else:
                resolved.append(expr)
        return resolved

    def iter_constrained_exprs(self, node):
        """Yield 'expr' values for mappings under node that have
        'constraints:'.

        Works for the direct form (expr + constraints as siblings on the
        check) and the nested 'search:' form (expr + constraints under
        'search').
        """
        if isinstance(node, dict):
            if "constraints" in node:
                yield node.get("expr")
            for value in node.values():
                yield from self.iter_constrained_exprs(value)
        elif isinstance(node, list):
            for item in node:
                yield from self.iter_constrained_exprs(item)

    def check_scenario_file(self, path):
        """Return a list of non-compliant findings for a single scenario file.

        Each finding is a dict: {check, expr, reason}.
        """
        try:
            with open(path, encoding="utf-8") as fd:
                data = yaml.safe_load(fd)
        except (yaml.YAMLError, OSError) as exc:
            logging.warning("skipping %s: failed to parse (%s)", path, exc)
            return []

        if not isinstance(data, dict) or "checks" not in data:
            return []

        variables = data.get("vars") or {}
        findings = []
        for check_name, check_body in (data.get("checks") or {}).items():
            for expr in self.iter_constrained_exprs(check_body):
                if expr is None:
                    findings.append({
                        "check": check_name,
                        "expr": None,
                        "reason": "constraints present but no 'expr' found",
                    })
                    continue

                patterns = self.resolve_expr(expr, variables)
                unresolved = [p for p in patterns if isinstance(p, str)
                              and p.startswith("$")]
                if unresolved:
                    findings.append({
                        "check": check_name,
                        "expr": expr,
                        "reason": f"could not resolve variable(s): "
                                  f"{', '.join(unresolved)}",
                    })
                    continue

                # A boolean (list) search is compliant if any of its patterns
                # captures the leading timestamp.
                for p in patterns:
                    if self.is_compliant(p):
                        continue

                    findings.append({
                        "check": check_name,
                        "expr": expr,
                        "reason": "search expression does not start with a "
                                  "timestamp capture group",
                    })

        return findings


class HotYValidate(TestCase):
    """ Validation for HotSOS YAML definitions i.e. events and scenarios. """

    @staticmethod
    def _discover_tests():
        # This list contains the full paths to all scenario test cases.
        # This information is used for reporting the number of avaliable
        # test cases.
        all_tests = []

        # A collection of all tests and their respective scenarios. Scenario
        # name is used as a key, where the value is list of tests associated
        # with the scenario.
        test_scenario_mappings = {}

        # Base directory that contains per-plugin scenario test trees. Used
        # to recover the plugin sub-root (e.g. 'kernel') from each yielded
        # absolute test path so that TemplatedTestGenerator receives the
        # correct test_defs_root value ('scenarios/<plugin>').
        tests_root_path = os.path.join(utils.DEFS_TESTS_DIR, 'scenarios')

        # Load the scenario tests one by one
        for testdef in YDefsLoader.get_scenario_test_files('scenarios'):
            logging.info("validating scenario test %s", testdef)

            # Add the discovered test to list of
            # all tests
            all_tests.append(testdef)

            # Recover the plugin sub-root from the absolute test path,
            # e.g. /.../defs/tests/scenarios/kernel/foo.yaml -> 'kernel'.
            rel = os.path.relpath(testdef, tests_root_path)
            subdir = rel.split(os.sep, 1)[0]

            # Load the test. The code needs to access some attributes
            # stored in the templated test class in order to be able to
            # determine the associated scenario.
            tg = utils.TemplatedTestGenerator(
                f'scenarios/{subdir}', testdef)

            # Determine the test's target scenario path.
            target_scenario_path = os.path.join(utils.DEFS_DIR,
                                                tg.test_defs_root,
                                                tg.target_path)

            # Add the test case's name to tests associated with the
            # scenario.
            if target_scenario_path in test_scenario_mappings:
                test_scenario_mappings[target_scenario_path].append(
                    testdef)
            else:
                test_scenario_mappings[target_scenario_path] = [testdef]

        return all_tests, test_scenario_mappings

    def scenarios_check_mappings(self):
        """Check for all YAML tests and scenarios to determine whether
        every scenario has at least one test.
        """

        # At this point, we have all the names of the scenarios which actually
        # have at least one test for it. Now, we're going to grab a list of all
        # scenario YAML files to compare them. We'll also check for a few
        # essential things we require in scenarios (e.g. having `checks` and
        # `conclusions` sections) as well.
        # Ensure the defs root is configured for YDefsLoader discovery.
        total_failed_expressions = 0
        expr_validator = SearchExpressionValidator()

        if not HotSOSConfig.plugin_yaml_defs:
            HotSOSConfig.plugin_yaml_defs = utils.DEFS_DIR

        # Use YDefsLoader to find all scenario YAML files
        scenario_files = list(YDefsLoader.get_scenario_files())

        all_tests, test_scenario_mappings = self._discover_tests()

        # This list will contain the names of the scenarios which does not have
        # a test case.
        scenarios_without_test = []

        # List of plugin requirement files
        scenarios_with_requires = []

        # The list of scenarios which does not have a `checks` section in it
        scenarios_without_checks_section = []

        # The list of scenarios which does not have a
        # `conclusions` section in it
        scenarios_without_conclusions_section = []

        # Try to load each scenario to determine its purpose.
        for scenario_file in scenario_files:
            logging.debug("processing scenario file [%s]", scenario_file)

            with open(scenario_file, encoding='utf-8') as sfilestream:
                sy = yaml.safe_load(sfilestream)

                # If the YAML file contains "requires" section
                # then it means the yaml is defining pre-conditions
                # for all the scenarios under the directory, so the
                # file itself is not a scenario.
                if "requires" in sy:
                    scenarios_with_requires.append(scenario_file)
                    logging.debug("\tscenario file [%s] is a folder-level"
                                  "pre-condition file, skipping",
                                  scenario_file)
                    # Skip the file.
                    continue

                # The rest, we can treat as scenarios and we should expect
                # them to have "checks" and "conditions" sections in each of
                # them. It does not make sense for a scenario to lack either
                # one of them. List if any, and report them altogether for
                # convenience.
                if "checks" not in sy:
                    scenarios_without_checks_section.append(scenario_file)
                    logging.debug("\tlint:no_checks [%s] has no `checks`"
                                  " section!", scenario_file)

                if "conclusions" not in sy:
                    scenarios_without_conclusions_section.append(scenario_file)
                    logging.debug("\tlint:no_conclusions [%s] has no "
                                  "`conclusions` section!", scenario_file)

            findings = expr_validator.check_scenario_file(scenario_file)
            for finding in findings:
                total_failed_expressions += 1
                logging.error("%s :: check '%s' :: %s\n    expr: %s",
                              scenario_file, finding["check"],
                              finding["reason"], finding["expr"])

            # We expect every single scenario to have at least one test
            # file. If there's none, store the scenario name for further
            # reporting.
            if scenario_file not in test_scenario_mappings:
                scenarios_without_test.append(scenario_file)

        # Report the scenarios without `checks` section, if any.
        self.assertEqual(
            len(scenarios_without_checks_section), 0,
            msg=f"The following scenario files does not have a `checks`"
            "section!:"
            f"{json.dumps(scenarios_without_checks_section, indent=4)}"
        )

        # Report the scenarios without `conclusions` section, if any.
        self.assertEqual(
            len(scenarios_without_conclusions_section), 0,
            msg=f"The following scenario files does not have a `conclusions`"
            "section!:"
            f"{json.dumps(scenarios_without_conclusions_section, indent=4)}"
        )

        # Finally, report the scenarios without a test.
        self.assertEqual(
            len(scenarios_without_test), 0,
            msg=f"Discovered {len(all_tests)} test(s), scenario count"
            f" is {len(scenario_files) - len(scenarios_with_requires)}, "
            f"scenario-test mapping count is {len(test_scenario_mappings)}."
            "The following scenario(s) does not have a test file:"
            f" {json.dumps(scenarios_without_test, indent=4)}")

        logging.info("results:")
        logging.info("checked %d scenarios and %d tests, all OK!",
                     len(scenario_files), len(all_tests))
        logging.info("checked search expressions from %d scenario(s); "
                     "%d non-compliant expression(s) found",
                     len(scenario_files),
                     total_failed_expressions)

    def scenarios_check_data_root_files(self):
        """Check that scenario tests which define a data-root do not share an
        absolute path in their `files:` section with any other test.

        Absolute paths in a test's `data-root.files` are written to the real
        filesystem location (they bypass the per-test temporary data root), so
        two tests sharing the same absolute path can clobber each other's data,
        particularly when tests run in parallel.
        """

        # Ensure the defs root is configured for YDefsLoader discovery.
        if not HotSOSConfig.plugin_yaml_defs:
            HotSOSConfig.plugin_yaml_defs = utils.DEFS_DIR

        # Mapping of absolute file path -> list of test files that define it in
        # their data-root `files:` section.
        abspath_to_tests = {}

        for testdef in YDefsLoader.get_scenario_test_files('scenarios'):
            with open(testdef, encoding='utf-8') as fd:
                ty = yaml.safe_load(fd) or {}

            data_root = ty.get('data-root')
            if not data_root:
                continue

            files = data_root.get('files')
            if not files:
                continue

            for path in files:
                if not os.path.isabs(path):
                    continue

                abspath_to_tests.setdefault(path, []).append(testdef)

        # An absolute path shared by more than one test is a conflict.
        shared = {path: sorted(tests)
                  for path, tests in abspath_to_tests.items()
                  if len(tests) > 1}

        self.assertEqual(
            len(shared), 0,
            msg="The following absolute path(s) are shared in the `files:` "
            "section of more than one scenario test data-root. Each test must "
            "use a unique absolute path (or a relative path) to avoid "
            f"conflicts:{json.dumps(shared, indent=4)}")

        logging.info("checked data-root files for absolute path conflicts, "
                     "all OK!")


if __name__ == "__main__":
    lvl = os.environ["HOTSOS_VALIDATE_YSCENARIOS_LOGLEVEL"] \
        if "HOTSOS_VALIDATE_YSCENARIOS_LOGLEVEL" in os.environ else "INFO"

    logging.basicConfig(level=lvl, stream=sys.stdout,
                        format="%(levelname)s: %(message)s")
    HotYValidate().scenarios_check_mappings()
    HotYValidate().scenarios_check_data_root_files()
