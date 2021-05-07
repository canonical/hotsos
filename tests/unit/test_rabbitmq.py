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
                'queues': {
                    'telegraf-telegraf-12': 'no queues',
                    'telegraf-telegraf-14': 'no queues',
                    '/': 'no queues',
                    'openstack': {
                        'rabbit@juju-52088b-0-lxd-11': '1137 (86.14%)',
                        'rabbit@juju-52088b-1-lxd-11': '108 (8.18%)',
                        'rabbit@juju-52088b-2-lxd-10': '75 (5.68%)',
                    },
                    'telegraf-telegraf-13': 'no queues',
                },
                'queue-connections': {
                    'rabbit@juju-52088b-0-lxd-11': 1316,
                    'rabbit@juju-52088b-1-lxd-11': 521,
                    'rabbit@juju-52088b-2-lxd-10': 454,
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
