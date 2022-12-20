import os

from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.rabbitmq import summary


class TestRabbitmqBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'rabbitmq'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/rabbitmq')


class TestRabbitmqSummary(TestRabbitmqBase):

    def test_get_summary(self):
        inst = summary.RabbitMQSummary()
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(list(inst.output.keys()),
                         ['config',
                          'dpkg',
                          'resources',
                          'services'])
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['dpkg'], ['rabbitmq-server 3.8.2-0ubuntu1.3'])
        self.assertEqual(actual['services'],
                         {'systemd': {
                              'enabled': ['epmd', 'rabbitmq-server']},
                          'ps': ['beam.smp (1)', 'epmd (1)',
                                 'rabbitmq-server (1)']})
        self.assertEqual(actual['config'],
                         {'cluster-partition-handling': 'ignore'})

    @mock.patch('hotsos.core.plugins.rabbitmq.report.CLIHelper')
    def test_summary_bionic(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()

        def fake_get_rabbitmqctl_report():
            path = os.path.join(HotSOSConfig.data_root,
                                "sos_commands/rabbitmq/rabbitmqctl_report."
                                "bionic")
            return open(path, 'r').readlines()

        mock_helper.return_value.rabbitmqctl_report.side_effect = \
            fake_get_rabbitmqctl_report

        expected = {
            'vhosts': [
                "/",
                "openstack",
                "telegraf-telegraf-12",
                "telegraf-telegraf-13",
                "telegraf-telegraf-14",
                ],
            'vhost-queue-distributions': {
                'openstack': {
                    'rabbit@juju-52088b-0-lxd-11': '1137 (86.14%)',
                    'rabbit@juju-52088b-1-lxd-11': '108 (8.18%)',
                    'rabbit@juju-52088b-2-lxd-10': '75 (5.68%)',
                },
            },
            'connections-per-host': {
                'rabbit@juju-52088b-0-lxd-11': 1316,
                'rabbit@juju-52088b-1-lxd-11': 521,
                'rabbit@juju-52088b-2-lxd-10': 454
            },
            'client-connections': {
                'cinder': {'cinder-scheduler': 9,
                           'cinder-volume': 24,
                           'mod_wsgi': 36},
                'neutron': {'neutron-dhcp-agent': 90,
                            'neutron-l3-agent': 21,
                            'neutron-lbaasv2-agent': 12,
                            'neutron-metadata-agent': 424,
                            'neutron-metering-agent': 12,
                            'neutron-openvswitch-agent': 296,
                            'neutron-server': 456},
                'nova': {'mod_wsgi': 34,
                         'nova-api-metadata': 339,
                         'nova-compute': 187,
                         'nova-conductor': 129,
                         'nova-consoleauth': 3,
                         'nova-scheduler': 216},
                'octavia': {'octavia-worker': 3},
            },
            'memory-used-mib': {
                'rabbit@juju-52088b-2-lxd-10': '558.877',
                'rabbit@juju-52088b-1-lxd-11': '605.539',
                'rabbit@juju-52088b-0-lxd-11': '1195.559',
            },
        }

        inst = summary.RabbitMQSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['resources'],
                         expected)

    def test_summary_focal(self):
        expected = {
            'vhosts': [
                '/',
                'openstack'],
            'vhost-queue-distributions': {
                'openstack': {
                    'rabbit@juju-04f1e3-1-lxd-5': '194 (100.00%)'
                    }},
            'connections-per-host': {
                'rabbit@juju-04f1e3-1-lxd-5': 159},
            'client-connections': {
                'neutron': {
                    'neutron-openvswitch-agent': 39,
                    'neutron-server': 37,
                    'neutron-l3-agent': 15,
                    'neutron-dhcp-agent': 12,
                    'neutron-metadata-agent': 6},
                'nova': {'nova-api-metadata': 24,
                         'nova-compute': 11,
                         'nova-conductor': 11,
                         'nova-scheduler': 4}}}

        inst = summary.RabbitMQSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['resources'],
                         expected)

    @mock.patch('hotsos.core.plugins.rabbitmq.report.CLIHelper')
    def test_get_summary_no_report(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.rabbitmqctl_report.return_value = []
        inst = summary.RabbitMQSummary()
        self.assertTrue('resources' not in
                        self.part_output_to_actual(inst.output))


@utils.load_templated_tests('scenarios/rabbitmq')
class TestRabbitmqScenarios(TestRabbitmqBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
