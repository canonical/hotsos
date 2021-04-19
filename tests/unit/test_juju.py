import glob
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
for f in glob.glob("plugins/juju/[0-9]*"):
    plugin = os.path.basename(f)
    module_name = "juju_{}".format(plugin)
    loader = SourceFileLoader(module_name, f)
    specs[plugin] = spec_from_loader(module_name, loader)

    globals()[module_name] = module_from_spec(specs[plugin])
    specs[plugin].loader.exec_module(globals()[module_name])


class TestJujuPlugin01juju(utils.BaseTestCase):

    juju_01juju = globals()["juju_01juju"]

    @mock.patch.object(juju_01juju, 'JUJU_MACHINE_INFO', {"machines": {}})
    def test_get_machine_info(self):
        self.juju_01juju.get_machine_info()
        expected = {'machines': {'running': ['33 (version=unknown)',
                                             '0 (version=unknown)']}}
        self.assertEquals(self.juju_01juju.JUJU_MACHINE_INFO, expected)


class TestJujuPlugin02charms(utils.BaseTestCase):

    juju_02charms = globals()["juju_02charms"]

    def test_get_charm_versions(self):
        with mock.patch.object(self.juju_02charms, 'CHARM_VERSIONS', {}):
            self.juju_02charms.get_charm_versions()
            expected = {}
            self.assertEquals(self.juju_02charms.CHARM_VERSIONS, expected)


class TestJujuPlugin03charms(utils.BaseTestCase):

    juju_03units = globals()["juju_03units"]

    def test_get_app_from_unit(self):
        with mock.patch.object(self.juju_03units, 'JUJU_UNIT_INFO',
                               {"units": {}}):
            unit = "foo-32"
            app = self.juju_03units.get_app_from_unit(unit)
            self.assertEquals(app, "foo")

    def test_get_unit_version(self):
        with mock.patch.object(self.juju_03units, 'JUJU_UNIT_INFO',
                               {"units": {}}):
            unit = "foo-32"
            version = self.juju_03units.get_unit_version(unit)
            self.assertEquals(version, 32)

    def test_get_unit_info(self):
        with mock.patch.object(self.juju_03units, 'JUJU_UNIT_INFO',
                               {"units": {}}):
            self.juju_03units.get_unit_info()
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
            self.maxDiff = None
            self.assertEquals(self.juju_03units.JUJU_UNIT_INFO,
                              {"units": expected})


class TestJujuPlugin04known_issues(utils.BaseTestCase):
    known_bugs = globals()["juju_04known_bugs"]

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    def test_detect_bug1910958(self):
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):

            result = self.known_bugs.detect_bug1910958()

        self.assertEqual(list(result.keys()), [1910958])
        self.assertEqual(list(result[1910958].keys()),
                         ['description', 'match'])
        self.assertEqual(len(result[1910958]['match'].split('\n')), 4,
                         "Expected 4 lines, but found: %s"
                         % result[1910958]['match'])
