from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.lxd import summary

from . import utils


class LXDTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'lxd'


class TestLXDSummary(LXDTestsBase):

    def test_summary_keys(self):
        expected = {'dpkg': {'lxd-agent-loader': '0.4'},
                    'instances': ['juju-04f1e3-1-lxd-0',
                                  'juju-04f1e3-1-lxd-1',
                                  'juju-04f1e3-1-lxd-2',
                                  'juju-04f1e3-1-lxd-3',
                                  'juju-04f1e3-1-lxd-4',
                                  'juju-04f1e3-1-lxd-5',
                                  'juju-04f1e3-1-lxd-6'],
                    'services': {'ps': [],
                                 'systemd': {
                                     'enabled': ['lxd-agent',
                                                 'lxd-agent-9p',
                                                 'snap.lxd.activate'],
                                     'static': ['snap.lxd.daemon',
                                                'snap.lxd.user-daemon'],
                                     'transient': ['snap.lxd.workaround']}},

                    'snaps': ['lxd 4.22']}
        inst = summary.LXDSummary()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


@utils.load_templated_tests('scenarios/lxd')
class TestLXDScenarios(LXDTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
