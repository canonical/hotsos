import mock

import os
import tempfile

import utils

from common import constants
from plugins.rabbitmq.pyparts import (
    cluster_checks,
    services,
)


class TestRabbitmqBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ["PLUGIN_NAME"] = "rabbitmq"


class TestRabbitmqServices(TestRabbitmqBase):

    def test_get_service_info_bionic(self):
        expected = {
            'services': ['beam.smp (1)', 'epmd (1)', 'rabbitmq-server (1)'],
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

        inst = services.RabbitMQServiceChecks()
        inst()
        issues = services.issues_utils._get_issues()

        self.assertEqual(inst.output, expected)
        self.assertEqual(issues,
                         {services.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-52088b-0-lxd-11 holds more '
                                     'than 2/3 of queues for 1/5 vhost(s)'),
                            'origin': 'rabbitmq.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'rabbitmq.01part',
                            'type': 'RabbitMQWarning'}]})

    @mock.patch.object(services, 'CLIHelper')
    def test_get_service_info_focal(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()

        def fake_get_rabbitmqctl_report():
            path = os.path.join(constants.DATA_ROOT,
                                "sos_commands/rabbitmq/rabbitmqctl_report."
                                "focal")
            return open(path, 'r').readlines()

        mock_helper.return_value.rabbitmqctl_report.side_effect = \
            fake_get_rabbitmqctl_report

        expected = {
            'services': ['beam.smp (1)', 'epmd (1)', 'rabbitmq-server (1)'],
            'resources': {
                'vhosts': [
                    '/',
                    'nagios-rabbitmq-server-0',
                    'nagios-rabbitmq-server-1',
                    'nagios-rabbitmq-server-2',
                    'openstack'
                    ],
                'vhost-queue-distributions': {
                    'nagios-rabbitmq-server-0': {
                        'rabbit@juju-ba2deb-7-lxd-9': '1 (100.00%)'
                        },
                    'openstack': {
                        'rabbit@juju-ba2deb-7-lxd-9': '1495 (100.00%)'
                        },
                    'nagios-rabbitmq-server-2': {
                        'rabbit@juju-ba2deb-7-lxd-9': '1 (100.00%)'
                        },
                    'nagios-rabbitmq-server-1': {
                        'rabbit@juju-ba2deb-7-lxd-9': '1 (100.00%)'
                        }
                },
                'connections-per-host': {
                    'rabbit@juju-ba2deb-7-lxd-9': 292
                },
                'client-connections': {'aodh': {'aodh-listener': 1,
                                                'aodh-notifier': 1},
                                       'ceilometer': {'ceilometer-polling': 1},
                                       'designate': {'designate-agent': 1,
                                                     'designate-api': 2,
                                                     'designate-central': 9,
                                                     'designate-mdns': 2,
                                                     'designate-producer': 7,
                                                     'designate-sink': 1,
                                                     'designate-worker': 3},
                                       'neutron': {
                                           'neutron-dhcp-agent': 4,
                                           'neutron-l3-agent': 6,
                                           'neutron-metadata-agent': 4,
                                           'neutron-openvswitch-agent': 27,
                                           'neutron-server': 131},
                                       'nova': {'nova-api-metadata': 33,
                                                'nova-compute': 6,
                                                'nova-conductor': 35,
                                                'nova-scheduler': 16},
                                       'octavia': {'octavia-worker': 2},
                                       },
                'cluster-partition-handling': 'ignore',
            }
        }

        inst = services.RabbitMQServiceChecks()
        inst()
        issues = services.issues_utils._get_issues()

        self.assertEqual(inst.output, expected)
        self.assertEqual(issues,
                         {services.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-ba2deb-7-lxd-9 holds more '
                                     'than 2/3 of queues for 1/5 vhost(s)'),
                            'origin': 'rabbitmq.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'rabbitmq.01part',
                            'type': 'RabbitMQWarning'}]})

    @mock.patch.object(services, 'CLIHelper')
    def test_get_service_info_no_report(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.rabbitmqctl_report.return_value = []
        inst = services.RabbitMQServiceChecks()
        inst()
        self.assertFalse("resources" in inst.output)

    def test_get_package_info(self):
        inst = services.get_rabbitmq_package_checker()
        inst()
        self.assertEqual(inst.output, None)


class TestRabbitmqClusterChecks(TestRabbitmqBase):

    @mock.patch.object(cluster_checks.issues_utils, 'add_issue')
    def test_cluster_checks_no_issue(self, mock_add_issue):
        inst = cluster_checks.RabbitMQClusterChecks()
        inst()
        self.assertEqual(inst.output, None)
        self.assertFalse(mock_add_issue.called)

    @mock.patch.object(cluster_checks.issues_utils, 'add_issue')
    def test_cluster_checks_w_partitions(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logdir = os.path.join(dtmp, 'var/log/rabbitmq')
            os.makedirs(logdir)
            with open(os.path.join(logdir, 'rabbit@foo.log'), 'w') as fd:
                fd.write("Mnesia(rabbit@node1): ** ERROR ** mnesia_event got "
                         "{inconsistent_database, running_partitioned_network"
                         ", rabbit@node2}\n")

            inst = cluster_checks.RabbitMQClusterChecks()
            inst()

        self.assertEqual(inst.output, None)
        self.assertTrue(mock_add_issue.called)
