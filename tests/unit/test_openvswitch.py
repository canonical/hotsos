import utils

from plugins.openvswitch.pyparts import (
    ovs_checks,
    ovs_resources,
)


class TestOpenvswitchPluginPartOpenvswitchServices(utils.BaseTestCase):

    def test_get_package_checks(self):
        expected = {'dpkg':
                    ['libc-bin 2.31-0ubuntu9.2',
                     'openvswitch-switch 2.13.3-0ubuntu0.20.04.1']}

        inst = ovs_resources.OpenvSwitchPackageChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_get_resource_checks(self):
        expected = {'services': ['ovs-vswitchd (1)',
                                 'ovsdb-client (1)',
                                 'ovsdb-server (1)']}

        inst = ovs_resources.OpenvSwitchServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)


class TestOpenvswitchPluginPartOpenvswitchDaemonChecks(utils.BaseTestCase):

    def test_common_checks(self):
        inst = ovs_checks.OpenvSwitchDaemonChecks()
        inst()
        self.assertEqual(inst.output, None)

    def test_dp_checks(self):
        expected = {'port-stats':
                    {'qr-aa623763-fd':
                     {'RX':
                      {'dropped': 1394875,
                       'packets': 309}}}}
        inst = ovs_checks.OpenvSwitchDPChecks()
        inst()
        self.assertEqual(inst.output, expected)
