import os

import utils

from common import known_bugs_utils

# Need this for plugin imports
utils.add_sys_plugin_path("juju")
from plugins.juju.parts.pyparts import (  # noqa E402
    machines,
    charms,
    units,
    known_bugs,
)


class TestJujuPluginPartServices(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_machine_info(self):
        expected = {'machines': {'running': ['33 (version=unknown)',
                                             '0 (version=unknown)']}}
        inst = machines.JujuMachineChecks()
        inst.get_machine_info()
        self.assertEquals(inst.output, expected)


class TestJujuPluginPartCharms(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_charm_versions(self):
        inst = charms.JujuCharmChecks()
        inst.get_charm_versions()
        self.assertIsNone(inst.output)


class TestJujuPluginPartUnits(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_app_from_unit_name(self):
        unit = "foo-32"
        inst = units.JujuUnitChecks()
        app = inst._get_app_from_unit_name(unit)
        self.assertEquals(app, "foo")

    def test_get_unit_version(self):
        unit = "foo-32"
        inst = units.JujuUnitChecks()
        version = inst._get_unit_version(unit)
        self.assertEquals(version, 32)

    def test_get_unit_info(self):
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
        inst = units.JujuUnitChecks()
        inst.get_unit_info()
        self.assertEquals(inst.output, {"units": expected})


class TestJujuPluginPartKnown_bugs(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ["PLUGIN_NAME"] = "juju"

    def test_detect_known_bugs(self):
        known_bugs.get_bug_checker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                      'desc':
                      ('Unit unit-rabbitmq-server-2 failed to start due '
                       'to members in relation 236 that cannot be '
                       'removed.'),
                      'origin': 'juju.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)
