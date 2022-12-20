import os
import subprocess

from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.host_helpers.filestat import FileFactory

DUMMY_CONFIG = """
[a-section]
a-key = 1023
b-key = 10-23
c-key = 2-8,10-31
"""


class TestHostNetworkingHelper(utils.BaseTestCase):

    def test_get_host_interfaces(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca']
        helper = host_helpers.HostNetworkingHelper()
        ifaces = helper.host_interfaces
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_host_interfaces_w_ns(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca', 'lo',
                    'fpr-984c22fd-6@if2', 'fg-c8dcce74-c4', 'lo',
                    'rfp-984c22fd-6@if2', 'qr-3a70b31c-3f', 'lo',
                    'ha-550dc175-c0', 'qg-14f81a43-69', 'sg-189f4c40-9d']
        helper = host_helpers.HostNetworkingHelper()
        ifaces = helper.host_interfaces_all
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_interface_with_addr_not_exists(self):
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('1.2.3.4')
        self.assertIsNone(iface)

    def test_get_interface_with_addr_exists(self):
        expected = {'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'state': 'UP',
                        'speed': 'unknown'}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    @mock.patch.object(host_helpers.network, 'CLIHelper')
    def test_get_interface_with_speed_exists(self, mock_cli):
        cli = host_helpers.CLIHelper()
        orig_ip_addr = cli.ip_addr()
        orig_ip_link = cli.ip_link()
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ethtool.return_value = ['Speed: 100000Mb/s\n']
        mock_cli.return_value.ip_addr.return_value = orig_ip_addr
        mock_cli.return_value.ip_link.return_value = orig_ip_link
        expected = {'br-ens3': {'addresses': ['10.0.0.128'],
                                'hwaddr': '22:c2:7b:1c:12:1b',
                                'state': 'UP',
                                'speed': '100000Mb/s'}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    def test_get_interface_stats(self):
        expected = {'rx': {'dropped': 0,
                           'errors': 0,
                           'overrun': 0,
                           'packets': 1628707},
                    'tx': {'dropped': 0,
                           'errors': 0,
                           'packets': 1520974}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.stats, expected)

    def test_get_interfaces_cached(self):
        helper = host_helpers.HostNetworkingHelper()
        helper.host_interfaces_all
        path = helper.global_cache_root
        for path in [os.path.join(path, 'interfaces.json'),
                     os.path.join(path, 'ns_interfaces.json')]:
            self.assertTrue(os.path.exists(path))

        addr = '10.0.0.128'
        iface = helper.get_interface_with_addr(addr)
        # do this to cache stats
        iface.stats
        helper = host_helpers.HostNetworkingHelper()
        data = helper.cache_load()
        iface_found = False
        for _iface in data:
            if _iface['name'] == iface.name:
                iface_found = True
                self.assertEqual(_iface['addresses'], [addr])

        with mock.patch.object(host_helpers.network, 'CLIHelper') as mock_cli:
            mock_cli.return_value = mock.MagicMock()
            helper = host_helpers.HostNetworkingHelper()
            iface = helper.get_interface_with_addr(addr)
            self.assertEqual(iface.addresses, [addr])
            # these should no longer be called
            self.assertFalse(mock_cli.return_value.ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_netns.called)
            self.assertFalse(mock_cli.return_value.ns_ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_link.called)
            self.assertFalse(mock_cli.return_value.ethtool.called)

        self.assertTrue(iface_found)


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
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2022-02-09")
        HotSOSConfig.use_all_logs = True
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2022-02-03")
        HotSOSConfig.max_logrotate_depth = 1000
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2019-05-17")

    def test_ns_ip_addr(self):
        ns = "qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5"
        out = host_helpers.cli.CLIHelper().ns_ip_addr(namespace=ns)
        self.assertEqual(type(out), list)
        self.assertEqual(len(out), 18)

    def test_udevadm_info_dev(self):
        out = host_helpers.cli.CLIHelper().udevadm_info_dev(device='/dev/vdb')
        self.assertEqual(out, [])

    @mock.patch.object(host_helpers.cli, 'subprocess')
    def test_ps(self, mock_subprocess):
        path = os.path.join(HotSOSConfig.data_root, "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        self.assertEqual(host_helpers.cli.CLIHelper().ps(), out)
        self.assertFalse(mock_subprocess.called)

    def test_get_date_local(self):
        HotSOSConfig.data_root = '/'
        self.assertEqual(type(host_helpers.cli.CLIHelper().date()), str)

    def test_get_date(self):
        self.assertEqual(host_helpers.cli.CLIHelper().date(), '1644509957')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 2021'})
    def test_get_date_no_tz(self):
        self.assertEqual(host_helpers.cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 -03 2021'})
    def test_get_date_w_numeric_tz(self):
        self.assertEqual(host_helpers.cli.CLIHelper().date(), '1616680505')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 UTC 2021'})
    def test_get_date_w_tz(self):
        self.assertEqual(host_helpers.cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 123UTC 2021'})
    def test_get_date_w_invalid_tz(self):
        self.assertEqual(host_helpers.cli.CLIHelper().date(), "")

    def test_ovs_ofctl_bin_w_errors(self):

        def fake_check_output(cmd, *_args, **_kwargs):
            if 'OpenFlow13' in cmd:
                return 'testdata'.encode(encoding='utf_8', errors='strict')
            else:
                raise subprocess.CalledProcessError(1, 'ofctl')

        HotSOSConfig.data_root = '/'
        with mock.patch.object(host_helpers.cli.subprocess,
                               'check_output') as \
                mock_check_output:
            mock_check_output.side_effect = fake_check_output

            # Test errors with eventual success
            helper = host_helpers.cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl_show(bridge='br-int'),
                             ['testdata'])

            mock_check_output.side_effect = \
                subprocess.CalledProcessError(1, 'ofctl')

            # Ensure that if all fails the result is always iterable
            helper = host_helpers.cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl_show(bridge='br-int'), [])


class TestSystemdHelper(utils.BaseTestCase):

    def test_service_factory(self):
        svc = host_helpers.systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644446297.0)

        self.assertEqual(host_helpers.systemd.ServiceFactory().noexist, None)

    def test_systemd_helper(self):
        expected = {'ps': ['nova-api-metadata (5)', 'nova-compute (1)'],
                    'systemd': {'enabled':
                                ['nova-api-metadata', 'nova-compute']}}
        s = host_helpers.systemd.SystemdHelper([r'nova\S+'])
        self.assertEqual(s.summary, expected)


class TestFileStatHelper(utils.BaseTestCase):

    @utils.create_data_root({'foo': 'bar'})
    def test_filestat_factory(self):
        fpath = os.path.join(HotSOSConfig.data_root, 'foo')
        fileobj = FileFactory().foo
        self.assertEqual(fileobj.mtime, os.path.getmtime(fpath))

        fileobj = FileFactory().noexist
        self.assertEqual(fileobj.mtime, 0)


class TestUptimeHelper(utils.BaseTestCase):

    def test_loadavg(self):
        self.assertEqual(host_helpers.UptimeHelper().loadavg,
                         "3.58, 3.27, 2.58")

    def test_uptime(self):
        self.assertEqual(host_helpers.UptimeHelper().seconds, 63660)
        self.assertEqual(host_helpers.UptimeHelper().hours, 17)

    @utils.create_data_root({'uptime':
                             (' 14:51:10 up 1 day,  6:27,  1 user,  '
                              'load average: 0.55, 0.73, 0.70')})
    def test_uptime_alt_format(self):
        self.assertEqual(host_helpers.UptimeHelper().seconds, 109620)
        self.assertEqual(host_helpers.UptimeHelper().hours, 30)


class TestSysctlHelper(utils.BaseTestCase):

    def test_sysctlhelper(self):
        self.assertEqual(getattr(host_helpers.SYSCtlFactory(),
                                 'net.core.somaxconn'), '4096')

    def test_sysctlconfhelper(self):
        path = os.path.join(HotSOSConfig.data_root, 'etc/sysctl.d')
        path = os.path.join(path, '50-nova-compute.conf')
        sysctl = host_helpers.SYSCtlConfHelper(path)
        setters = {'net.ipv4.neigh.default.gc_thresh1': '128',
                   'net.ipv4.neigh.default.gc_thresh2': '28672',
                   'net.ipv4.neigh.default.gc_thresh3': '32768',
                   'net.ipv6.neigh.default.gc_thresh1': '128',
                   'net.ipv6.neigh.default.gc_thresh2': '28672',
                   'net.ipv6.neigh.default.gc_thresh3': '32768',
                   'net.nf_conntrack_max': '1000000',
                   'net.netfilter.nf_conntrack_buckets': '204800',
                   'net.netfilter.nf_conntrack_max': '1000000'}
        self.assertEqual(sysctl.setters, setters)
        self.assertEqual(sysctl.unsetters, {})


class TestAPTPackageHelper(utils.BaseTestCase):

    def test_core_packages(self):
        expected = {'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_helpers.APTPackageHelper(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.15")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_all_packages(self):
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_helpers.APTPackageHelper(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.15',
                    'systemd-container 245.4-4ubuntu3.15',
                    'systemd-sysv 245.4-4ubuntu3.15',
                    'systemd-timesyncd 245.4-4ubuntu3.15']
        obj = host_helpers.APTPackageHelper(["systemd"])
        self.assertEqual(obj.all_formatted, expected)


class TestSnapPackageHelper(utils.BaseTestCase):

    def test_all(self):
        expected = {'core20': '20220114'}
        obj = host_helpers.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core20"), "20220114")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("lxd"), "4.22")

    def test_formatted(self):
        expected = ['core20 20220114']
        obj = host_helpers.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all_formatted, expected)


class TestConfigHelper(utils.BaseTestCase):

    @utils.create_data_root({'test.conf': DUMMY_CONFIG})
    def test_sectionalconfig_base(self):
        conf = os.path.join(HotSOSConfig.data_root, 'test.conf')
        cfg = host_helpers.SectionalConfigBase(conf)
        self.assertTrue(cfg.exists)
        self.assertEqual(cfg.get('a-key'), '1023')
        self.assertEqual(cfg.get('a-key', section='a-section'), '1023')
        self.assertEqual(cfg.get('a-key', section='missing-section'), None)
        self.assertEqual(cfg.get('a-key', expand_to_list=True), [1023])

        expanded = cfg.get('b-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(10, 24)))
        self.assertEqual(cfg.squash_int_range(expanded), '10-23')

        expanded = cfg.get('c-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(2, 9)) + list(range(10, 32)))
        self.assertEqual(cfg.squash_int_range(expanded), '2-8,10-31')
