import os

from tests.unit import utils

from plugin_extensions.pacemaker import summary


class TestPacemakerBase(utils.BaseTestCase):
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ["PLUGIN_NAME"] = "pacemaker]"
        os.environ['DATA_ROOT'] = os.path.join(utils.TESTS_DIR,
                                               'fake_data_root/pacemaker')


class TestPacemakerSummary(TestPacemakerBase):

    def test_dpkg(self):
        expected = ['corosync 3.0.3-2ubuntu2.1',
                    'crmsh 4.2.0-2ubuntu1',
                    'pacemaker 2.0.3-3ubuntu4.3',
                    'pacemaker-cli-utils 2.0.3-3ubuntu4.3',
                    'pacemaker-common 2.0.3-3ubuntu4.3',
                    'pacemaker-resource-agents 2.0.3-3ubuntu4.3']
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEquals(actual["dpkg"], expected)

    def test_services(self):
        expected = {'ps': ['corosync (1)', 'pacemakerd (1)'],
                    'systemd': {
                        'enabled': [
                            'corosync',
                            'pacemaker']
        }}
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEquals(actual["services"], expected)
