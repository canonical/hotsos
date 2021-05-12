import mock

import utils

utils.add_sys_plugin_path("rabbitmq")
from plugins.rabbitmq.parts import (  # noqa E402
    services,
)


class TestRabbitmqPluginPartServices(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
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

        services.get_rabbitmq_service_checker()()
        self.maxDiff = None
        self.assertEqual(services.RABBITMQ_INFO, expected)

    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_package_info(self):
        expected = {}
        services.get_rabbitmq_package_checker()()
        self.assertEqual(services.RABBITMQ_INFO, expected)
