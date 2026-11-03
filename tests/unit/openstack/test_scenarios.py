import os
import shutil
import tempfile

from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
from hotsos.core.ycheck.scenarios import YScenarioChecker
from tests.unit import utils
from tests.unit.openstack.test_openstack import TestOpenstackBase


@utils.load_templated_tests('scenarios/openstack')
class TestOpenstackScenarios(TestOpenstackBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """

    @utils.create_data_root({'sos_commands/dpkg/dpkg_-l':
                             'ii python3-neutron 2:28.0.0-0ubuntu1.1 all\n'})
    @utils.global_search_context
    def test_lp2156566_no_agent_preserves_later_sibling(self, global_searcher):
        """An absent OVS agent must not suppress another Neutron scenario."""
        relative_dir = os.path.join('scenarios', 'openstack', 'neutron',
                                    'bugs')
        source = os.path.join(HotSOSConfig.plugin_yaml_defs, relative_dir,
                              'lp2156566.yaml')
        with tempfile.TemporaryDirectory() as defs:
            target = os.path.join(defs, relative_dir)
            os.makedirs(target)
            shutil.copyfile(source, os.path.join(target, 'lp2156566.yaml'))
            with open(os.path.join(target, 'zz-later-sibling.yaml'), 'w',
                      encoding='utf-8') as fd:
                fd.write("""
checks:
  code_installed:
    apt: python3-neutron
conclusions:
  independent:
    decision: code_installed
    raises:
      type: OpenstackWarning
      message: Later sibling still runs.
""")
            HotSOSConfig.plugin_yaml_defs = defs
            HotSOSConfig.scenario_filter = None
            HotSOSConfig.force_mode = False
            checker = YScenarioChecker(global_searcher)
            checker.load()
            self.assertEqual([s.name for s in checker.scenarios],
                             ['lp2156566', 'zz-later-sibling'])
            self.assertFalse(
                checker.scenarios[0].checks['affected_package'].result)
            checker.run(load=False)
            self.assertEqual(IssuesManager().load_bugs(), {})
            issues = IssuesManager().load_issues()['potential-issues']
            self.assertEqual([issue['message'] for issue in issues],
                             ['Later sibling still runs.'])
