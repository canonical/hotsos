from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.microcloud import summary

from . import utils

SNAPS = """
Name        Version                 Rev    Tracking       Publisher      Notes
core24      20241217                739    latest/stable  canonical**    base
lxd         5.21.3-75def3c          32455  5.21/stable    canonical**    in-cohort
microceph   19.2.0+snap2fbf0bad05   1271   latest/stable  canonical**    in-cohort
microcloud  2.1.0-d29fd90           1281   latest/stable  canonical**    in-cohort
microovn    24.03.2+snapa2c59c105b  667    latest/stable  canonical**    in-cohort
snapd       2.67.1                  23771  latest/stable  canonical**    snapd
"""  # noqa


class MicroCloudTestsBase(utils.BaseTestCase):
    """ Custom base testcase that sets microcloud plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = "microcloud"


class TestMicroCloudSummary(MicroCloudTestsBase):
    """Unit tests for microcloud summary"""

    @utils.create_data_root({"sos_commands/snap/snap_list_--all": SNAPS})
    def test_summary_keys(self):
        expected = {
            "snaps": [
                "lxd 5.21.3-75def3c (5.21/stable)",
                "microceph 19.2.0+snap2fbf0bad05 (latest/stable)",
                "microcloud 2.1.0-d29fd90 (latest/stable)",
                "microovn 24.03.2+snapa2c59c105b (latest/stable)",
            ]
        }
        inst = summary.MicroCloudSummary()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


@utils.load_templated_tests("scenarios/microcloud")
class TestMicroCloudScenarios(MicroCloudTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
