import os
import shutil
import tempfile

import mock

import utils

# Need this for plugin imports
utils.add_sys_plugin_path("openvswitch")
from plugins.openvswitch.parts import (  # noqa E402
    ovs_checks,
    ovs_resources,
)


class TestOpenvswitchPluginPartOpenvswitchServices(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ovs_resources, "OVS_INFO", {})
    def test_get_package_checks(self):
        expected = {'dpkg':
                    ['libc-bin 2.23-0ubuntu11.2',
                     'openvswitch-switch 2.9.5-0ubuntu0.18.04.1~cloud0']}

        ovs_resources.get_package_checks()()
        self.assertEqual(ovs_resources.OVS_INFO,
                         expected)

    @mock.patch.object(ovs_resources, "OVS_INFO", {})
    def test_get_resource_checks(self):
        expected = {'services': ['ovs-vswitchd (1)',
                                 'ovsdb-client (1)',
                                 'ovsdb-server (1)']}

        ovs_resources.get_service_checker()()
        self.assertEqual(ovs_resources.OVS_INFO,
                         expected)


class TestOpenvswitchPluginPartOpenvswitchDaemonChecks(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    @mock.patch.object(ovs_checks, "OVS_INFO", {})
    def test_get_checks(self):
        expected = {'port-stats':
                    {'qr-1d849332-80':
                     {'RX':
                      {'dropped': 1394875,
                       'packets': 309}}}}
        with mock.patch.object(ovs_checks.issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            [c() for c in ovs_checks.get_checks()]
            self.assertEqual(ovs_checks.OVS_INFO,
                             expected)
