import utils

from plugins.openvswitch.pyparts import (
    ovs_checks,
    ovs_resources,
)


class TestOpenvswitchPluginPartOpenvswitchServices(utils.BaseTestCase):

    def test_get_package_checks(self):
        expected = {'dpkg':
                    ['libc-bin 2.23-0ubuntu11.2',
                     'openvswitch-switch 2.9.5-0ubuntu0.18.04.1~cloud0']}

        inst = ovs_resources.get_package_checks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_get_resource_checks(self):
        expected = {'services': ['ovs-vswitchd (1)',
                                 'ovsdb-client (1)',
                                 'ovsdb-server (1)']}

        inst = ovs_resources.get_service_checker()
        inst()
        self.assertEqual(inst.output, expected)


class TestOpenvswitchPluginPartOpenvswitchDaemonChecks(utils.BaseTestCase):

    def test_common_checks(self):
        inst = ovs_checks.OpenvSwitchDaemonChecksCommon()
        inst()
        self.assertEqual(inst.output, None)

    def test_vswitchd_checks(self):
        inst = ovs_checks.OpenvSwitchvSwitchdChecks()
        inst()
        self.assertEqual(inst.output, None)

    def test_dp_checks(self):
        expected = {'port-stats':
                    {'qr-1d849332-80':
                     {'RX':
                      {'dropped': 1394875,
                       'packets': 309}}}}
        inst = ovs_checks.OpenvSwitchDPChecks()
        inst()
        self.assertEqual(inst.output, expected)
