import contextlib
import os
import tempfile
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.plugin_extensions.rabbitmq import event_checks, summary

from . import utils


RABBITMQ_ERROR_LOGS = """
2025-01-01 01:52:19.909819+00:00 [error] <0.30051.866>  operation queue.declare caused a connection exception internal_error: "Cannot declare a queue 'queue 'notifications.critical' in vhost 'openstack'' on node 'rabbit@host1': {vhost_supervisor_not_running,<<\"openstack\">>}"
2025-01-01 01:52:19.914542+00:00 [error] <0.29014.862>  operation queue.declare caused a connection exception internal_error: "Cannot declare a queue 'queue 'notifications.debug' in vhost 'openstack'' on node 'rabbit@host1': {vhost_supervisor_not_running,<<\"openstack\">>}"
2025-01-01 01:52:19.922978+00:00 [error] <0.26024.848>  operation queue.declare caused a connection exception internal_error: "Cannot declare a queue 'queue 'notifications.info' in vhost 'openstack'' on node 'rabbit@host1': {vhost_supervisor_not_running,<<\"openstack\">>}"
2025-01-01 02:35:35.906159+00:00 [error] <0.20881.847> operation none caused a channel exception precondition_failed: delivery acknowledgement on channel 1 timed out. Timeout value used: 1800000 ms. This timeout value can be configured, see consumers doc guide to learn more
2025-01-02 13:07:54.866061+00:00 [error] <0.275.0> Mnesia('rabbit@host1'): ** ERROR ** mnesia_event got {inconsistent_database, running_partitioned_network, 'rabbit@host2'}
"""  # noqa


class TestRabbitmqBase(utils.BaseTestCase):
    """ Custom base testcase that sets rabbitmq plugin context. """
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'rabbitmq'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/rabbitmq')


class TestRabbitmqSummary(TestRabbitmqBase):
    """ Unit tests for RabbitMQ summary. """
    def test_get_summary(self):
        inst = summary.RabbitMQSummary()
        self.assertTrue(inst.is_runnable())
        self.assertEqual(list(inst.output.keys()),
                         ['services',
                          'dpkg',
                          'config',
                          'resources'])
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['dpkg'], ['rabbitmq-server 3.8.2-0ubuntu1.3'])
        self.assertEqual(actual['services'],
                         {'systemd': {
                              'enabled': ['epmd', 'rabbitmq-server']},
                          'ps': ['beam.smp (1)', 'epmd (1)',
                                 'rabbitmq-server (1)']})
        self.assertEqual(actual['config'],
                         {'cluster-partition-handling': 'ignore'})

    @mock.patch('hotsos.core.plugins.rabbitmq.report.CLIHelperFile')
    def test_summary_bionic(self, mock_helper):
        class FakeCLIHelperFile(contextlib.AbstractContextManager):
            """ fake clihelper """
            @staticmethod
            def rabbitmqctl_report():
                return os.path.join(HotSOSConfig.data_root,
                                    "sos_commands/rabbitmq/rabbitmqctl_report."
                                    "bionic")

            @staticmethod
            def __exit__(*_args, **_kwargs):
                return False

        mock_helper.side_effect = FakeCLIHelperFile
        expected = {
            'vhosts': [
                "/",
                "openstack",
                "telegraf-telegraf-12",
                "telegraf-telegraf-13",
                "telegraf-telegraf-14"],
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
                    'rabbit@juju-04f1e3-1-lxd-5': '194 (100.00%)'}},
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

    @mock.patch('hotsos.core.plugins.rabbitmq.report.CLIHelperFile')
    def test_get_summary_no_report(self, mock_helper):
        with tempfile.NamedTemporaryFile() as ftmp:
            class FakeCLIHelperFile(contextlib.AbstractContextManager):
                """ fake clihelper """
                @staticmethod
                def rabbitmqctl_report():
                    return ftmp.name

                @staticmethod
                def __exit__(*_args, **_kwargs):
                    return False

            mock_helper.side_effect = FakeCLIHelperFile
            inst = summary.RabbitMQSummary()
            self.assertTrue('resources' not in
                            self.part_output_to_actual(inst.output))


class TestRabbitMQEvents(TestRabbitmqBase):
    """ Unit tests for rmq events. """
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors.yaml',
                                        'events/rabbitmq'))
    @utils.create_data_root({'var/log/rabbitmq/rabbit@node1.log':
                             RABBITMQ_ERROR_LOGS})
    def test_error_checks(self):
        expected = {'connection-exception': {'2025-01-01': {
                                                'internal_error': 3}},
                    'delivery-ack-timeout': {'2025-01-01': {'1800000': 1}},
                    'mnesia-error-event': {'2025-01-02': {
                        ("inconsistent_database, running_partitioned_network, "
                         "'rabbit@host2'"): 1}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.RabbitMQEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual, expected)


@utils.load_templated_tests('scenarios/rabbitmq')
class TestRabbitmqScenarios(TestRabbitmqBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
