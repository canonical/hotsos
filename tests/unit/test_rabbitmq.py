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
        expected = {'services': ['beam.smp (1)']}
        services.get_rabbitmq_service_checker()()
        self.assertEqual(services.RABBITMQ_INFO, expected)

    @mock.patch.object(services, "RABBITMQ_INFO", {})
    def test_get_package_info(self):
        expected = {}
        services.get_rabbitmq_package_checker()()
        self.assertEqual(services.RABBITMQ_INFO, expected)
