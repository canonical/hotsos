from unittest import mock

from hotsos.core.config import HotSOSConfig
import hotsos.core.plugins.openstack as openstack_core
from hotsos.core.plugins.openstack import sunbeam
from tests.unit import utils
from tests.unit.openstack.test_openstack import TestOpenstackBase


class TestOpenstackSunbeam(TestOpenstackBase):
    """ Unit tests for OpenStack Sunbeam . """

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/sunbeam'

    def test_not_controller(self):
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/openstack'
        sunbeaminfo = sunbeam.SunbeamInfo()
        self.assertFalse(sunbeaminfo.is_controller)
        self.assertDictEqual(sunbeaminfo.pods, {})
        self.assertDictEqual(sunbeaminfo.statefulsets, {})

    def test_pods(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        expected = {'Running': ['certificate-authority-0',
                                'cinder-0',
                                'cinder-mysql-router-0',
                                'glance-0',
                                'glance-mysql-router-0',
                                'horizon-0',
                                'horizon-mysql-router-0',
                                'keystone-0',
                                'keystone-mysql-router-0',
                                'modeloperator-6f8f4577b4-9zhvc',
                                'mysql-0',
                                'neutron-0',
                                'neutron-mysql-router-0',
                                'nova-0',
                                'nova-api-mysql-router-0',
                                'nova-cell-mysql-router-0',
                                'nova-mysql-router-0',
                                'ovn-central-0',
                                'ovn-relay-0',
                                'placement-0',
                                'placement-mysql-router-0',
                                'rabbitmq-0',
                                'traefik-0',
                                'traefik-public-0']}
        self.assertDictEqual(sunbeaminfo.pods, expected)

    def test_statefulsets(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        expected = {'complete': ['certificate-authority',
                                 'cinder',
                                 'cinder-mysql-router',
                                 'glance',
                                 'glance-mysql-router',
                                 'horizon',
                                 'horizon-mysql-router',
                                 'keystone',
                                 'keystone-mysql-router',
                                 'mysql',
                                 'neutron',
                                 'neutron-mysql-router',
                                 'nova',
                                 'nova-api-mysql-router',
                                 'nova-cell-mysql-router',
                                 'nova-mysql-router',
                                 'ovn-central',
                                 'ovn-relay',
                                 'placement',
                                 'placement-mysql-router',
                                 'rabbitmq',
                                 'traefik',
                                 'traefik-public'],
                    'incomplete': []}
        self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"readyReplicas": 1,"replicas": 1}}]}'})
    def test_statefulsets_w_complete(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': ['traefik-public'],
                        'incomplete': []}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"readyReplicas": 0,"replicas": 1}}]}'})
    def test_statefulsets_w_incomplete(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': [],
                        'incomplete': ['traefik-public']}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)

    @utils.create_data_root(
        {'sos_commands/kubernetes/cluster-info/openstack/'
         'k8s_kubectl_get_-o_json_--namespace_openstack_statefulsets':
         '{"apiVersion": "v1","items": [{"metadata": '
         '{"name": "traefik-public"},"status": '
         '{"replicas": 1}}]}'})
    def test_statefulsets_w_missing_readreplicas_key(self):
        sunbeaminfo = sunbeam.SunbeamInfo()
        with mock.patch.object(sunbeaminfo, 'is_controller',
                               return_value=True):
            expected = {'complete': [],
                        'incomplete': ['traefik-public']}
            self.assertDictEqual(sunbeaminfo.statefulsets, expected)


class TestOpenstackSunbeamPluginCore(TestOpenstackBase):
    """ Unit tests for OpenStack Sunbeam plugin core. """

    def test_project_catalog_snap_packages(self):
        HotSOSConfig.data_root = 'tests/unit/fake_data_root/sunbeam'
        ost_base = openstack_core.OpenstackBase()
        core = {'openstack':
                {'version': '2024.1', 'channel': '2024.1/stable'},
                'openstack-hypervisor':
                {'version': '2024.1', 'channel': '2024.1/stable'}}
        self.assertEqual(ost_base.snaps.core, core)
