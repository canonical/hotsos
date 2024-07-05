import os
import glob
import json
from unittest import TestCase
import logging
import sys

import yaml
from tests.unit import utils


class HotYValidate(TestCase):
    """ Validation for HotSOS YAML definitions i.e. events and scenarios. """

    def scenarios_check_mappings(self):
        """Check for all YAML tests and scenarios to determine whether
        every scenario has at least one test.
        """

        tests_root_path = os.path.join(utils.DEFS_TESTS_DIR, 'scenarios')
        scenarios_root_path = os.path.join(utils.DEFS_DIR, 'scenarios')

        # This list contains the full paths to all scenario test cases.
        # This information is used for reporting the number of avaliable
        # test cases.
        all_tests = []

        # A collection of all tests and their respective scenarios. Scenario
        # name is used as a key, where the value is list of tests associated
        # with the scenario.
        test_scenario_mappings = {}

        # Iterate over all subdirectories of `hotsos/defs/tests` and try to
        # discover all the available test cases.
        for subdir in os.listdir(tests_root_path):
            logging.info("processing directory [%s/%s]", tests_root_path,
                         subdir)
            tests = utils.find_all_templated_tests(
                os.path.join(tests_root_path, subdir))

            # Load the scenario tests one by one
            for testdef in tests:
                # Add the discovered test to list of
                # all tests
                all_tests.append(testdef)

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

        # At this point, we have all the names of the scenarios which actually
        # have at least one test for it. Now, we're going to grab a list of all
        # scenario YAML files to compare them. We'll also check for a few
        # essential things we require in scenarios (e.g. having `checks` and
        # `conclusions` sections) as well.
        scenario_files = glob.glob(scenarios_root_path + '/**/*.yaml',
                                   recursive=True)

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

            with open(scenario_file) as sfilestream:
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

        logging.info("processed [%d] scenarios and [%d] tests, all OK!",
                     len(scenario_files), len(all_tests))


if __name__ == "__main__":
    lvl = os.environ["HOTSOS_VALIDATE_YSCENARIOS_LOGLEVEL"] \
        if "HOTSOS_VALIDATE_YSCENARIOS_LOGLEVEL" in os.environ else "INFO"

    logging.basicConfig(level=lvl, stream=sys.stdout)
    HotYValidate().scenarios_check_mappings()
