import mock

import os
import shutil
import tempfile
import utils

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
    def test_get_service_info(self):
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
            },
        }

        with mock.patch.object(services.issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            services.get_rabbitmq_service_checker()()
            issues = services.issues_utils._get_issues()
        self.maxDiff = None
        self.assertEqual(services.RABBITMQ_INFO, expected)
        self.assertEqual(issues,
                         {services.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'RabbitMQWarning': 'rabbit@juju-52088b-0-lxd-11 '
                            'holds more than 2/3 of queues'}]})

    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_package_info(self):
        expected = {}
        services.get_rabbitmq_package_checker()()
        self.assertEqual(services.RABBITMQ_INFO, expected)
