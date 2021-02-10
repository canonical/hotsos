import os

import mock
import shutil
import tempfile
import utils

# Must be set prior to import
os.environ["DATA_ROOT"] = os.path.join(os.path.curdir, "fake_data_root")
from common import helpers  # noqa


IP_ADDR = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo            
       valid_lft forever preferred_lft forever                                                                                                                                                                             
    inet6 ::1/128 scope host                                                                                 
       valid_lft forever preferred_lft forever    
2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 8958 qdisc fq_codel state UP group default qlen 1000
    link/ether fa:16:3e:54:af:42 brd ff:ff:ff:ff:ff:ff                                                                                                                                                                     
    inet 10.5.3.81/16 brd 10.5.255.255 scope global dynamic ens3
       valid_lft 60260sec preferred_lft 60260sec  
    inet6 fe80::f816:3eff:fe54:af42/64 scope link 
       valid_lft forever preferred_lft forever
""" # noqa


class TestHelpers(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.data_root = tempfile.mkdtemp()
        os.symlink(self.data_root, os.environ["DATA_ROOT"])

    def tearDown(self):
        super().tearDown()
        os.remove(os.environ["DATA_ROOT"])
        shutil.rmtree(self.data_root)

    @mock.patch.object(helpers, 'subprocess')
    def test_get_ip_addr(self, mock_subprocess):
        path = os.path.join(self.data_root,
                            "sos_commands/networking/ip_-d_address")
        os.makedirs(os.path.dirname(path))
        with open(path, 'w') as fd:
            fd.write(IP_ADDR + "\n")

        ret = helpers.get_ip_addr()
        self.assertEquals(ret, [line + '\n' for line in IP_ADDR.split('\n')])
