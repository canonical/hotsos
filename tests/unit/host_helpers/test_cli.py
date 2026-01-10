import os
import subprocess
from dataclasses import dataclass
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import (
    cli as host_cli,
    catalog,
    common as cli_common,
)

from .. import utils


KUBECTL_GET_OUT = """
{
    "apiVersion": "v1",
    "items": [                            
        {
            "apiVersion": "v1",
            "kind": "Service"
        }]
}
"""  # noqa


class TestCLIHelper(utils.BaseTestCase):
    """
    NOTE: remember that a data_root is configured so helpers will always
    use fake_data_root if possible. If you write a test that wants to
    test a scenario where no data root is set (i.e. no sosreport) you need
    to unset it as part of the test.
    """

    def test_journalctl(self):
        HotSOSConfig.use_all_logs = False
        HotSOSConfig.max_logrotate_depth = 7
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2022-02-09")
        HotSOSConfig.use_all_logs = True
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2022-02-03")
        HotSOSConfig.max_logrotate_depth = 1000
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2019-05-17")

    def test_ns_ip_addr(self):
        ns = "qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5"
        out = host_cli.CLIHelper().ns_ip_addr(namespace=ns)
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 18)

    def test_udevadm_info_dev(self):
        out = host_cli.CLIHelper().udevadm_info_dev(device='/dev/vdb')
        self.assertEqual(out, [])

    @mock.patch.object(cli_common, 'subprocess')
    def test_ps(self, mock_subprocess):
        path = os.path.join(HotSOSConfig.data_root, "ps")
        with open(path, 'r', encoding='utf-8') as fd:
            out = fd.readlines()

        self.assertEqual(host_cli.CLIHelper().ps(), out)
        self.assertFalse(mock_subprocess.called)

    def test_get_date_local(self):
        HotSOSConfig.data_root = '/'
        self.assertEqual(type(host_cli.CLIHelper().date()), str)

    def test_get_date(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1644509957')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 2021'})
    def test_get_date_no_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 -03 2021'})
    def test_get_date_w_numeric_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616680505')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 UTC 2021'})
    def test_get_date_w_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 123UTC 2021'})
    def test_get_date_w_invalid_tz(self):
        with self.assertLogs(logger='hotsos', level='ERROR') as log:
            self.assertEqual(host_cli.CLIHelper().date(), "")
            # If invalid date, log.error() will have been called
            self.assertEqual(len(log.output), 1)
            self.assertIn('has invalid date string', log.output[0])

    def test_ovs_ofctl_bin_w_errors(self):

        def fake_run(cmd, *_args, **_kwargs):
            if 'OpenFlow13' in cmd:
                m = mock.MagicMock()
                m.returncode = 0
                m.stdout = 'testdata'.encode(encoding='utf_8', errors='strict')
                m.stderr = ''
                return m

            raise subprocess.CalledProcessError(1, 'ofctl')

        HotSOSConfig.data_root = '/'
        with mock.patch.object(cli_common.subprocess, 'run') as \
                mock_run:
            mock_run.side_effect = fake_run

            # Test errors with eventual success
            helper = host_cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl(command='show', args='br-int'),
                             ['testdata'])

            mock_run.side_effect = \
                subprocess.CalledProcessError(1, 'ofctl')

            # Ensure that if all fails the result is always iterable
            helper = host_cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl(command='show', args='br-int'),
                             [])

    @mock.patch.object(host_cli.CLIHelper, 'command_catalog',
                       {'sleep': [host_cli.BinCmd('time sleep 2')]})
    def test_cli_timeout(self):
        cli = host_cli.CLIHelper()
        orig_cfg = HotSOSConfig.CONFIG
        try:
            # ensure bin command executed
            HotSOSConfig.data_root = '/'
            HotSOSConfig.command_timeout = 1
            out = cli.sleep()
            # a returned [] implies an exception was raised and caught
            self.assertEqual(out, [])
        finally:
            # restore
            HotSOSConfig.set(**orig_cfg)

    @mock.patch.object(host_cli.CLIHelper, 'command_catalog',
                       {'sleep': [host_cli.BinCmd('time sleep 1')]})
    def test_cli_no_timeout(self):
        cli = host_cli.CLIHelper()
        orig_cfg = HotSOSConfig.CONFIG
        try:
            # ensure bin command executed
            HotSOSConfig.data_root = '/'
            out = cli.sleep()
            self.assertEqual(len(out), 2)
        finally:
            # restore
            HotSOSConfig.set(**orig_cfg)

    def test_clitempfile(self):
        with host_cli.CLIHelperFile() as cli:
            self.assertEqual(os.path.basename(cli.date()), 'date')

        with host_cli.CLIHelperFile() as cli:
            orig_cfg = HotSOSConfig.CONFIG
            try:
                # ensure bin command executed
                HotSOSConfig.data_root = '/'
                self.assertEqual(cli.date(), cli.output_file)
            finally:
                # restore
                HotSOSConfig.set(**orig_cfg)

    @staticmethod
    @mock.patch.object(cli_common, 'subprocess')
    def test_kubectl_get_bincmd(mock_subprocess):
        HotSOSConfig.data_root = '/'
        mock_out = mock.MagicMock()
        mock_subprocess.run.return_value = mock_out
        mock_out.stdout = b"{}"
        mock_out.stderr = b""
        host_cli.CLIHelper().kubectl_get(namespace='openstack',
                                         opt='pods', subopts='')
        cmd = ['kubectl', 'get', '--namespace', 'openstack', 'pods', '-o',
               'json']
        mock_subprocess.run.assert_called_with(cmd, timeout=300,
                                               capture_output=True,
                                               check=False)

    @staticmethod
    @mock.patch.object(cli_common, 'subprocess')
    def test_kubectl_logs_bincmd(mock_subprocess):
        HotSOSConfig.data_root = '/'
        host_cli.CLIHelper().kubectl_logs(namespace='openstack',
                                          opt='neutron-0',
                                          subopts='-c neutron-server')
        cmd = ['kubectl', 'logs', '--namespace', 'openstack', 'neutron-0',
               '-c', 'neutron-server']
        mock_subprocess.run.assert_called_with(cmd, timeout=300,
                                               capture_output=True,
                                               check=False)

    @utils.create_data_root({'sos_commands/kubernetes/cluster-info/openstack/'
                             'podlogs/neutron-0/kubectl_--namespace_'
                             'openstack_logs_neutron-0_-c_neutron-server':
                             'SUCCESS!'})
    def test_kubectl_logs_filecmd(self):
        out = host_cli.CLIHelper().kubectl_logs(namespace='openstack',
                                                opt='neutron-0',
                                                subopts='-c neutron-server')
        self.assertEqual(out, ['SUCCESS!'])

    @utils.create_data_root({'sos_commands/kubernetes/cluster-info/openstack/'
                             'podlogs/neutron-0/microk8s_kubectl_--namespace_'
                             'openstack_logs_neutron-0_-c_neutron-server':
                             'SUCCESS!'})
    def test_kubectl_logs_filecmd_microk8s(self):
        out = host_cli.CLIHelper().kubectl_logs(namespace='openstack',
                                                opt='neutron-0',
                                                subopts='-c neutron-server')
        self.assertEqual(out, ['SUCCESS!'])

    @utils.create_data_root({'sos_commands/kubernetes/services/kubectl_'
                             '--kubeconfig_.etc.kubernetes.admin.conf_get_'
                             '-o_json_--namespace_'
                             'kubernetes-dashboard_services': KUBECTL_GET_OUT})
    def test_kubectl_get_filecmd(self):
        out = host_cli.CLIHelper().kubectl_get(
                                     namespace='kubernetes-dashboard',
                                     opt='services')
        expected = {'apiVersion': 'v1', 'items': [{'apiVersion': 'v1',
                                                   'kind': 'Service'}]}
        self.assertEqual(out, expected)


class TestCommandAffinity(utils.BaseTestCase):
    """ Tests for command affinity. """

    CMD_KWARGS = {'ovs_appctl':
                  {'command': 'dpctl/dump-dps'},
                  'ovs_ofctl':
                  {'command': 'dump-flows', 'args': 'br-data'},
                  'ovs_vsctl_list':
                  {'table': 'bridge'},
                  'ovs_vsctl_get':
                  {'table': 'Open_vSwitch', 'record': '.',
                   'column': 'other_config'},
                  'ethtool':
                  {'interface': 'ens3'},
                  'ns_ip_addr':
                  {'namespace': 'fip-32981f34-497a-4fae-914a-8576055c8d0d'}}

    # Allow the code to use affinity for this test
    @mock.patch.object(host_cli.os, 'environ', {})
    def test_cmd_affinity(self):

        class CmdBase(cli_common.BinCmd):
            """ fake command base """

            @property
            def _affinity_info(self):
                return self.__class__, self.cmd

        class CmdA(CmdBase):
            """ fake command """

        class CmdB(CmdBase):
            """ fake command """

        @dataclass
        class FakeOut:
            """
            Fake Popen output
            """
            stdout: str
            stderr: str
            returncode: int

        checked = []
        with mock.patch.object(cli_common.subprocess, 'run') as mock_run:
            for cmd in [(CmdA, 'cmd_a'), (CmdB, 'cmd_b')]:
                cmd_cls, cmd_key = cmd
                mock_run.return_value = FakeOut(f'i am {cmd_key}'.
                                                encode('utf-8'),
                                                ''.encode('utf-8'), 0)
                source = cmd_cls(cmd_key)
                self.assertEqual(cmd_cls.CMD_AFFINITY, None)
                self.assertEqual(source().value, [f'i am {cmd_key}'])
                source.affinity.set(cmd_key)
                self.assertTrue(source.affinity.matches(cmd_key))
                self.assertEqual(list(source.CMD_AFFINITY), [cmd_key])
                checked.append(source)

        self.assertEqual(len(checked), 2)
        # ensure each cmd only has affinity info for itself
        self.assertTrue(all(len(list(s.CMD_AFFINITY)) == 1
                            for s in checked))

    # Allow the code to use affinity for this test
    @mock.patch.object(host_cli.os, 'environ', {})
    def test_all_cmds(self):
        cmds = set()
        cmd_no_output = set()
        skipped = set()
        for cmd in catalog.CommandCatalog():
            kwargs = self.CMD_KWARGS.get(cmd, {})
            try:
                if getattr(host_cli.CLIHelper(), cmd)(**kwargs):
                    cmds.add(cmd)
                else:
                    cmd_no_output.add(cmd)

            except KeyError:
                skipped.add(cmd)

        # These are commands where the data root does not contain info to
        # return as output of the command and therefore an affinity was not
        # set for he command source.
        expected = set(['udevadm_info_dev',
                        'kubectl_get',
                        'docker_ps',
                        'ceph_osd_df_tree_json_decoded',
                        'ovn_nbctl_show',
                        'ovn_sbctl_list',
                        'pebble_services',
                        'sunbeam_cluster_list_yaml_decoded',
                        'ceph_daemon_osd_config_show',
                        'ceph_report_json_decoded',
                        'ps_axo_flags',
                        'docker_images',
                        'ovn_nbctl_list',
                        'pacemaker_crm_status',
                        'rabbitmqctl_report',
                        'ceph_pg_dump_json_decoded',
                        'ovn_sbctl_show',
                        'ceph_mgr_module_ls',
                        'ceph_health_detail_json_decoded',
                        'sunbeam_cluster_list',
                        'ceph_status_json_decoded',
                        'ceph_daemon_osd_dump_mempools',
                        'ceph_osd_crush_dump_json_decoded',
                        'ceph_versions',
                        'ceph_mon_dump_json_decoded',
                        'ceph_osd_dump_json_decoded',
                        'ceph_df_json_decoded',
                        'kubectl_logs',
                        ])
        self.assertEqual(cmd_no_output, expected)
        self.assertEqual(skipped, set())
        # These are commands where the data root DOES contain info to
        # return as output of the command and therefore an affinity WAS
        # set for he command source.
        expected = set(['apt_config_dump',
                        'apparmor_status',
                        'ceph_volume_lvm_list',
                        'date',
                        'df',
                        'dmesg',
                        'dpkg_l',
                        'ethtool',
                        'hostname',
                        'hostnamectl',
                        'ip_netns',
                        'ip_addr',
                        'ip_link',
                        'ls_lanR_sys_block',
                        'lscpu',
                        'lsof_Mnlc',
                        'lxd_buginfo',
                        'numactl',
                        'ns_ip_addr',
                        'ovs_appctl',
                        'ovs_vsctl_get',
                        'ovs_vsctl_list',
                        'ovs_vsctl_list_br',
                        'ps',
                        'pro_status',
                        'snap_list_all',
                        'sysctl_all',
                        'systemctl_status_all',
                        'systemctl_list_units',
                        'systemctl_list_unit_files',
                        'udevadm_info_exportdb',
                        'uname',
                        'uptime'])
        self.assertEqual(cmds, expected.union(set(['ovs_ofctl'])))

        affinity = set()
        for cmd in cmds:
            for source in catalog.CommandCatalog()[cmd]:
                if source.CMD_AFFINITY:
                    affinity.update(list(source.CMD_AFFINITY.keys()))

        cmds.remove('ovs_ofctl')  # no affinity for this one
        self.assertEqual(cmds, expected)
        self.assertEqual(affinity, expected)
