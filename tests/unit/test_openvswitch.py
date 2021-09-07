import os
import utils

from plugins.openvswitch.pyparts import (
    ovs_checks,
    ovs_resources,
)


class TestOpenvswitchBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ["PLUGIN_NAME"] = "openvswitch"


class TestOpenvswitchPluginPartOpenvswitchServices(TestOpenvswitchBase):

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


class TestOpenvswitchPluginPartOpenvswitchDaemonChecks(TestOpenvswitchBase):

    def test_common_checks(self):
        expected = {'daemon-checks': {
                        'logs': {
                            'ovs-vswitchd': {'WARN': {'2021-06-29': 1,
                                                      '2021-07-19': 1}},
                            'ovsdb-server': {'ERR': {'2021-07-16': 1},
                                             'WARN': {'2021-07-28': 1}}},
                        'ovs-vswitchd': {
                            'bridge-no-such-device': {
                                '2021-06-29': {
                                    'tapd4b5494a-b1': 1}},
                            'netdev-linux-no-such-device': {
                                '2021-07-19': {
                                    'tap4b02cb1d-8b': 1}
                                }}}}
        inst = ovs_checks.OpenvSwitchDaemonChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_dp_checks(self):
        expected = {'port-stats':
                    {'qr-aa623763-fd':
                     {'RX':
                      {'dropped': 1394875,
                       'packets': 309}}}}
        inst = ovs_checks.OpenvSwitchDPChecks()
        inst()
        self.assertEqual(inst.output, expected)
