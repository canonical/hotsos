import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import sysctl as host_sysctl

from .. import utils


class TestSysctlHelper(utils.BaseTestCase):
    """ Unit tests for sysctl helper """
    def test_sysctlhelper(self):
        self.assertEqual(getattr(host_sysctl.SYSCtlFactory(),
                                 'net.core.somaxconn'), '4096')

    def test_sysctlconfhelper(self):
        path = os.path.join(HotSOSConfig.data_root, 'etc/sysctl.d')
        path = os.path.join(path, '50-nova-compute.conf')
        sysctl = host_sysctl.SYSCtlConfHelper(path)
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
