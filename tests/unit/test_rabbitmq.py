import mock

import os
import shutil
import tempfile
import utils

from common import constants

utils.add_sys_plugin_path("rabbitmq")
from plugins.rabbitmq.parts import (  # noqa E402
    services,
)


class TestRabbitmqPluginPartServices(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_service_info_bionic(self):
        expected = {
            'services': ['beam.smp (1)'],
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
                'queue-connections': {
                    'rabbit@juju-52088b-0-lxd-11': 1316,
                    'rabbit@juju-52088b-1-lxd-11': 521,
                    'rabbit@juju-52088b-2-lxd-10': 454
                },
                'memory-used-mib': {
                    'rabbit@juju-52088b-2-lxd-10': '558.877',
                    'rabbit@juju-52088b-1-lxd-11': '605.539',
                    'rabbit@juju-52088b-0-lxd-11': '1195.559',
                },
                'cluster-partition-handling': 'ignore',
            },
        }

        with mock.patch.object(services.issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            services.get_rabbitmq_service_checker()()
            issues = services.issues_utils._get_issues()

        self.assertEqual(services.RABBITMQ_INFO, expected)
        self.assertEqual(issues,
                         {services.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-52088b-0-lxd-11 holds more '
                                     'than 2/3 of queues for 1/5 vhost(s)'),
                            'origin': 'testplugin.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'testplugin.01part',
                            'type': 'RabbitMQWarning'}]})

    @mock.patch.object(services.cli_helpers, "get_rabbitmqctl_report")
    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_service_info_focal(self, mock_rabbitmqctl_report):

        def fake_get_rabbitmqctl_report():
            path = os.path.join(constants.DATA_ROOT,
                                "sos_commands/rabbitmq/rabbitmqctl_report."
                                "focal")
            return open(path, 'r').readlines()

        mock_rabbitmqctl_report.side_effect = fake_get_rabbitmqctl_report

        expected = {'services': ['beam.smp (1)'],
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
                        'queue-connections': {
                            'rabbit@juju-ba2deb-7-lxd-9': 292},
                        'cluster-partition-handling': 'ignore',
                    }
                    }

        with mock.patch.object(services.issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            services.get_rabbitmq_service_checker()()
            issues = services.issues_utils._get_issues()

        self.assertEqual(services.RABBITMQ_INFO, expected)
        self.assertEqual(issues,
                         {services.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'RabbitMQWarning',
                            'desc': ('rabbit@juju-ba2deb-7-lxd-9 holds more '
                                     'than 2/3 of queues for 1/5 vhost(s)'),
                            'origin': 'testplugin.01part'},
                           {'desc': 'Cluster partition handling is currently '
                                    'set to ignore. This is potentially '
                                    'dangerous and a setting of '
                                    'pause_minority is recommended.',
                            'origin': 'testplugin.01part',
                            'type': 'RabbitMQWarning'}]})

    @mock.patch.object(services.cli_helpers, "get_rabbitmqctl_report")
    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_service_info_no_report(self, mock_rabbitmqctl_report):
        mock_rabbitmqctl_report.return_value = []
        services.get_rabbitmq_service_checker()()
        self.assertFalse("resources" in services.RABBITMQ_INFO)

    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_package_info(self):
        expected = {}
        services.get_rabbitmq_package_checker()()
        self.assertEqual(services.RABBITMQ_INFO, expected)
