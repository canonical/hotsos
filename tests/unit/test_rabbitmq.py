import os
import tempfile

import mock

from tests.unit import utils

from core import constants
from core.ycheck.bugs import YBugChecker
from core.issues.issue_utils import MASTER_YAML_ISSUES_FOUND_KEY
from plugins.rabbitmq.pyparts import (
    cluster_checks,
    service_info,
    service_event_checks,
)

RABBITMQ_LOGS = """
Mirrored queue 'rmq-two-queue' in vhost '/': Stopping all nodes on master shutdown since no synchronised slave is available

Discarding message {'$gen_call',{<0.753.0>,#Ref<0.989368845.173015041.56949>},{info,[name,pid,slave_pids,synchronised_slave_pids]}} from <0.753.0> to <0.943.0> in an old incarnation (3) of this node (1)

2020-05-18 06:55:37.324 [error] <0.341.0> Mnesia(rabbit@warp10): ** ERROR ** mnesia_event got {inconsistent_database, running_partitioned_network, rabbit@hostname2}
"""  # noqa


class TestRabbitmqBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ['PLUGIN_NAME'] = 'rabbitmq'
        os.environ['DATA_ROOT'] = os.path.join(utils.TESTS_DIR,
                                               'fake_data_root/rabbitmq')


class TestRabbitmqServiceInfo(TestRabbitmqBase):

    @mock.patch('core.plugins.rabbitmq.RabbitMQChecksBase.plugin_runnable',
                False)
    def test_get_service_info_none(self):
        inst = service_info.RabbitMQServiceChecks()
        inst()
        self.assertFalse(inst.plugin_runnable)
        self.assertEqual(inst.output, None)

    def test_get_service_info(self):
        inst = service_info.RabbitMQServiceChecks()
        inst()
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(inst.output,
                         {'dpkg': ['rabbitmq-server 3.8.2-0ubuntu1.3'],
                          'services': {
                             'systemd': {
                                'enabled': ['epmd', 'rabbitmq-server']},
                             'ps': ['beam.smp (1)', 'epmd (1)',
                                    'rabbitmq-server (1)']}})


class TestRabbitmqClusterChecks(TestRabbitmqBase):

    @mock.patch.object(cluster_checks, 'CLIHelper')
    def test_cluster_checks_bionic(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()

        def fake_get_rabbitmqctl_report():
            path = os.path.join(constants.DATA_ROOT,
                                "sos_commands/rabbitmq/rabbitmqctl_report."
                                "bionic")
            return open(path, 'r').readlines()

        mock_helper.return_value.rabbitmqctl_report.side_effect = \
            fake_get_rabbitmqctl_report

        expected = {
            'resources': {
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
                'cluster-partition-handling': 'ignore',
            },
        }

        inst = cluster_checks.RabbitMQClusterChecks()
        inst()
        issues = cluster_checks.issue_utils._get_plugin_issues()

        self.assertEqual(inst.output, expected)
        self.assertEqual(issues,
                         {MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-52088b-0-lxd-11 holds more '
                                     'than 2/3 of queues for 1/5 vhost(s).'),
                            'origin': 'rabbitmq.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'rabbitmq.01part',
                            'type': 'RabbitMQWarning'}]})

    def test_cluster_checks_focal(self):
        expected = {'resources': {
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
                                     'nova-scheduler': 4}},
                        'cluster-partition-handling': 'ignore'}}

        inst = cluster_checks.RabbitMQClusterChecks()
        inst()
        issues = cluster_checks.issue_utils._get_plugin_issues()

        self.assertEqual(inst.output, expected)
        self.assertEqual(issues,
                         {MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-04f1e3-1-lxd-5 holds more '
                                     'than 2/3 of queues for 1/2 vhost(s).'),
                            'origin': 'rabbitmq.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'rabbitmq.01part',
                            'type': 'RabbitMQWarning'}]})

    @mock.patch.object(cluster_checks, 'CLIHelper')
    def test_get_service_info_no_report(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.rabbitmqctl_report.return_value = []
        inst = cluster_checks.RabbitMQClusterChecks()
        inst()
        self.assertIsNone(inst.output)


class TestRabbitmqBugChecks(TestRabbitmqBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('rabbtimq-server.yaml'))
    @mock.patch('core.ycheck.bugs.add_known_bug')
    def test_1943937(self, mock_add_known_bug):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/rabbitmq/rabbit@test.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write("operation queue.declare caused a channel exception "
                         "not_found: failed to perform operation on queue "
                         "'test_exchange_queue' in vhost "
                         "'nagios-rabbitmq-server-0' due to timeout")

            YBugChecker()()
            self.assertTrue(mock_add_known_bug.called)
            msg = ('Known RabbitMQ issue where queues get stuck and clients '
                   'trying to use them will just keep timing out. This stops '
                   'many services in the cloud from working correctly. '
                   'Resolution requires you to stop all RabbitMQ servers '
                   'before starting them all again at the same time. A '
                   'rolling restart or restarting them simultaneously will '
                   'not work. See bug for more detail.')
            mock_add_known_bug.assert_has_calls([mock.call('1943937', msg)])


class TestRabbitmqEventChecks(TestRabbitmqBase):

    @mock.patch.object(service_event_checks.issue_utils, 'add_issue')
    def test_service_event_checks(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/rabbitmq/rabbit@test.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(RABBITMQ_LOGS)

            inst = service_event_checks.RabbitMQEventChecks()
            inst()
            self.assertEqual(inst.output, None)
            self.assertTrue(mock_add_issue.called)
