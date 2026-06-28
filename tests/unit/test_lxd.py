from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.lxd import summary

from . import utils


LXD6X_BUGINFO = """
## Instances
```
+------------+--------+----------+----------------------+--------------+-----------+-----------+
|  PROJECT   |  NAME  |  STATE   |         IPV4         |     IPV6     |   TYPE    | SNAPSHOTS |
+------------+---------+---------+----------------------+--------------+-----------+-----------+
| altproj    | ctr2    | STOPPED |                      |              | CONTAINER | 0         |
+------------+---------+---------+----------------------+--------------+-----------+-----------+
| default    | testctr | RUNNING | 10.44.9.117 (eth0)   |              | CONTAINER | 0         |
+------------+---------+---------+----------------------+--------------+-----------+-----------+
```

## Images

"""  # noqa

LXD6X_SNAPS = """
Name                       Version                         Rev    Tracking         Publisher           Notes
lxd                        6.9-a34e1d7                     39858  6/stable         canonical✓          -
"""  # noqa


class LXDTestsBase(utils.BaseTestCase):
    """ Custom base testcase that sets lxd plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'lxd'


class TestLXDSummary(LXDTestsBase):
    """ Unit tests for lxd summary """
    def test_summary_keys(self):
        """Test that lxd summary output contains expected keys."""
        expected = {'dpkg': ['lxd-agent-loader 0.4'],
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

                    'snaps': ['lxd 4.22 (latest/stable)']}
        inst = summary.LXDSummary()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @utils.create_data_root({'sos_commands/lxd/lxd.buginfo': LXD6X_BUGINFO,
                             'sos_commands/snap/snap_list_--all': LXD6X_SNAPS})
    def test_summary_keys_lxd_6x(self):
        """Test that lxd 6.x summary output contains expected keys."""
        expected = {'instances': ['ctr2', 'testctr'],
                    'snaps': ['lxd 6.9-a34e1d7 (6/stable)']}
        inst = summary.LXDSummary()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


@utils.load_templated_tests('scenarios/lxd')
class TestLXDScenarios(LXDTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
