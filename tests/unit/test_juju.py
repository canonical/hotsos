import mock
import os
import shutil
import tempfile

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

from common import known_bugs_utils


# need this for non-standard import
specs = {}
for plugin in ["01juju", "02charms", "03units", "04known_bugs"]:
    loader = SourceFileLoader("juju_{}".format(plugin),
                              "plugins/juju/{}".format(plugin))
    specs[plugin] = spec_from_loader("juju_{}".format(plugin), loader)

juju_01juju = module_from_spec(specs["01juju"])
specs["01juju"].loader.exec_module(juju_01juju)

juju_02charms = module_from_spec(specs["02charms"])
specs["02charms"].loader.exec_module(juju_02charms)

juju_03units = module_from_spec(specs["03units"])
specs["03units"].loader.exec_module(juju_03units)

juju_04known_bugs = module_from_spec(specs["04known_bugs"])
specs["04known_bugs"].loader.exec_module(juju_04known_bugs)


class TestJujuPlugin01juju(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(juju_01juju, 'JUJU_MACHINE_INFO', {"machines": {}})
    def test_get_machine_info(self):
        juju_01juju.get_machine_info()
        expected = {'machines': {'running': ['33 (version=unknown)',
                                             '0 (version=unknown)']}}
        self.assertEquals(juju_01juju.JUJU_MACHINE_INFO, expected)


class TestJujuPlugin02charms(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(juju_02charms, 'CHARM_VERSIONS', {})
    def test_get_charm_versions(self):
        juju_02charms.get_charm_versions()
        expected = {}
        self.assertEquals(juju_02charms.CHARM_VERSIONS, expected)


class TestJujuPlugin03charms(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(juju_03units, 'JUJU_UNIT_INFO', {"units": {}})
    def test_get_app_from_unit(self):
        unit = "foo-32"
        app = juju_03units.get_app_from_unit(unit)
        self.assertEquals(app, "foo")

    @mock.patch.object(juju_03units, 'JUJU_UNIT_INFO', {"units": {}})
    def test_get_unit_version(self):
        unit = "foo-32"
        version = juju_03units.get_unit_version(unit)
        self.assertEquals(version, 32)

    @mock.patch.object(juju_03units, 'JUJU_UNIT_INFO', {"units": {}})
    def test_get_unit_info(self):
        juju_03units.get_unit_info()
        expected = {'local': ['filebeat-24', 'neutron-gateway-0',
                              'ntp-0'],
                    'lxd': ['ceph-mon-0',
                            'ceph-osd-no-fixed-wal-7',
                            'ceph-radosgw-0',
                            'ceph-radosgw-hacluster-0',
                            'cinder-0',
                            'cinder-ceph-0',
                            'cinder-hacluster-0',
                            'elasticsearch-1',
                            'filebeat-39',
                            'glance-0',
                            'glance-hacluster-0',
                            'grafana-0',
                            'keystone-0',
                            'keystone-hacluster-0',
                            'landscape-client-80',
                            'memcached-0',
                            'mysql-0',
                            'mysql-hacluster-0',
                            'neutron-api-0',
                            'neutron-api-hacluster-0',
                            'neutron-openvswitch-25',
                            'neutron-openvswitch-octavia-0',
                            'nova-cloud-controller-0',
                            'nova-cloud-controller-hacluster-0',
                            'nova-compute-0',
                            'nrpe-container-31',
                            'ntp-71',
                            'octavia-0',
                            'octavia-hacluster-5',
                            'openstack-dashboard-0',
                            'openstack-dashboard-hacluster-0',
                            'prometheus-0',
                            'prometheus-ceph-exporter-0',
                            'prometheus-openstack-exporter-0',
                            'rabbitmq-server-0'],
                    'stopped': ['nrpe-0', 'rabbitmq-server-2',
                                'rabbitmq-server-3']}
        self.assertEquals(juju_03units.JUJU_UNIT_INFO, {"units": expected})


class TestJujuPlugin04known_issues(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    def test_detect_known_bugs(self):
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            juju_04known_bugs.detect_known_bugs()
            expected = {"known-bugs": ['https://pad.lv/1910958']}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)
