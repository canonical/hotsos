import os
import mock
import tempfile

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

os.environ["VERBOSITY_LEVEL"] = "1000"

# need this for non-standard import
specs = {}
for plugin in ["01openstack", "02vm_info", "03nova_external_events",
               "04package_versions", "05network", "06_service_features",
               "07_cpu_pinning_check"]:
    loader = SourceFileLoader("ost_{}".format(plugin),
                              "plugins/openstack/{}".format(plugin))
    specs[plugin] = spec_from_loader("ost_{}".format(plugin), loader)

ost_01openstack = module_from_spec(specs["01openstack"])
specs["01openstack"].loader.exec_module(ost_01openstack)

ost_02vm_info = module_from_spec(specs["02vm_info"])
specs["02vm_info"].loader.exec_module(ost_02vm_info)

ost_03nova_external_events = module_from_spec(specs["03nova_external_events"])
specs["03nova_external_events"].loader.exec_module(
                                              ost_03nova_external_events)

ost_04package_versions = module_from_spec(specs["04package_versions"])
specs["04package_versions"].loader.exec_module(ost_04package_versions)

ost_05network = module_from_spec(specs["05network"])
specs["05network"].loader.exec_module(ost_05network)

ost_06_service_features = module_from_spec(specs["06_service_features"])
specs["06_service_features"].loader.exec_module(ost_06_service_features)

ost_07_cpu_pinning_check = module_from_spec(specs["07_cpu_pinning_check"])
specs["07_cpu_pinning_check"].loader.exec_module(ost_07_cpu_pinning_check)


IP_LINK_SHOW = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo            
       valid_lft forever preferred_lft forever                                                                                                                                                                             
    inet6 ::1/128 scope host                                                                                 
       valid_lft forever preferred_lft forever
6: enp59s0f0: <BROADCAST,MULTICAST,SLAVE,UP,LOWER_UP> mtu 9000 qdisc mq master bond1 state UP mode DEFAULT group default qlen 1000
    link/ether ac:1f:6b:9e:d8:44 brd ff:ff:ff:ff:ff:ff promiscuity 0
    bond_slave state ACTIVE mii_status UP link_failure_count 0 perm_hwaddr ac:1f:6b:9e:d8:44 queue_id 0 ad_aggregator_id 1 ad_actor_oper_port_state 63 ad_partner_oper_port_state 63 addrgenmode none numtxqueues 480 numrxqueues 60 gso_max_size 65536 gso_max_segs 65535
    RX: bytes  packets  errors  dropped overrun mcast
    566216505914 198725012 {}       0       0       10354794
    TX: bytes  packets  errors  dropped carrier collsns
    784224322216 226755877 0       0       0       0 
11: bond1: <BROADCAST,MULTICAST,MASTER,UP,LOWER_UP> mtu 9000 qdisc noqueue state UP mode DEFAULT group default qlen 1000
    link/ether ac:1f:6b:9e:d8:44 brd ff:ff:ff:ff:ff:ff promiscuity 0
    bond mode 802.3ad miimon 100 updelay 0 downdelay 0 use_carrier 1 arp_interval 0 arp_validate none arp_all_targets any primary_reselect always fail_over_mac none xmit_hash_policy layer2 resend_igmp 1 num_grat_arp 1 all_slaves_active 0 min_links 0 lp_interval 1 packets_per_slave 1 lacp_rate fast ad_select stable ad_aggregator 1 ad_num_ports 2 ad_actor_key 21 ad_partner_key 17 ad_partner_mac 44:39:39:ff:40:09 ad_actor_sys_prio 65535 ad_user_port_key 0 ad_actor_system 00:00:00:00:00:00 tlb_dynamic_lb 1 addrgenmode eui64 numtxqueues 16 numrxqueues 16 gso_max_size 65536 gso_max_segs 65535
    RX: bytes  packets  errors  dropped overrun mcast
    3726156143468 1168699571 0       {}       0       22418946
    TX: bytes  packets  errors  dropped carrier collsns
    4547600932334 1238029513 0       0       0       0
13: bond1.4003@bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc noqueue state UP mode DEFAULT group default qlen 1000
    link/ether ac:1f:6b:9e:d8:44 brd ff:ff:ff:ff:ff:ff promiscuity 0
    vlan protocol 802.1Q id 4003 <REORDER_HDR> addrgenmode eui64 numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535
    RX: bytes  packets  errors  dropped overrun mcast
    3672302080166 840215658 0       0       0       36333
    TX: bytes  packets  errors  dropped carrier collsns
    4509045041821 831579034 0       0       0       0
""" # noqa


IP_ADDR_SHOW = """
45: bond1: <BROADCAST,MULTICAST,MASTER,UP,LOWER_UP> mtu 1500 qdisc noqueue master br-bond1 state UP group default qlen 1000
    link/ether 45:1d:b2:89:bd:35 brd ff:ff:ff:ff:ff:ff promiscuity 1 
    bond mode 802.3ad miimon 100 updelay 0 downdelay 0 use_carrier 1 arp_interval 0 arp_validate none arp_all_targets any primary_reselect always fail_over_mac none xmit_hash_policy layer3+4 resend_igmp 1 num_grat_arp 1 all_slaves_active 0 min_links 0 lp_interval 1 packets_per_slave 1 lacp_rate fast ad_select stable ad_aggregator 1 ad_num_ports 1 ad_actor_key 9 ad_partner_key 1 ad_partner_mac 00:00:00:00:00:00 ad_actor_sys_prio 65535 ad_user_port_key 0 ad_actor_system 00:00:00:00:00:00 tlb_dynamic_lb 1 
    bridge_slave state forwarding priority 32 cost 4 hairpin off guard off root_block off fastleave off learning on flood on 
    inet6 fe80::36ed:1bff:feb9:ad46/64 scope link 
       valid_lft forever preferred_lft forever
150: tap40f8453b-31: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc pfifo_fast master ovs-system state UNKNOWN group default qlen 1000
    link/ether fe:16:3e:6d:8f:a7 brd ff:ff:ff:ff:ff:ff promiscuity 1 
    tun 
    openvswitch_slave 
    inet6 fe80::fc16:3eff:fe6d:8fa7/64 scope link 
       valid_lft forever preferred_lft forever
46: br-bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether 45:1d:b2:89:bd:35 brd ff:ff:ff:ff:ff:ff promiscuity 0 
    bridge forward_delay 1500 hello_time 200 max_age 2000 ageing_time 30000 stp_state 0 priority 32768 vlan_filtering 0 vlan_protocol 802.1Q 
    inet 10.10.101.33/26 brd 10.10.101.63 scope global br-bond1
       valid_lft forever preferred_lft forever
    inet6 fe80::36ed:1bff:feb9:ad46/64 scope link 
       valid_lft forever preferred_lft forever
151: tap1fd66df1-42: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc pfifo_fast master ovs-system state UNKNOWN group default qlen 1000
    link/ether fe:16:3e:0f:3e:9a brd ff:ff:ff:ff:ff:ff promiscuity 1 
    tun 
    openvswitch_slave 
    inet6 fe80::fc16:3eff:fe0f:3e9a/64 scope link 
       valid_lft forever preferred_lft forever
"""  # noqa

PS = """
nova      1285  0.6  2.6 294340 106260 ?       Ss   Feb17  11:14 /usr/bin/python3 /usr/bin/nova-api-metadata --config-file=/etc/nova/nova.conf --log-file=/var/log/nova/nova-api-metadata.log
root      1295  0.9  2.6 311772 106048 ?       Ss   Feb17  16:05 /usr/bin/python3 /usr/bin/neutron-ovn-metadata-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/neutron_ovn_metadata_agent.ini --log-file=/var/log/neutron/neutron-ovn-metadata-agent.log
root      1305  0.0  0.0  21776  3488 ?        Ss   Feb17   0:00 bash /etc/systemd/system/jujud-unit-nova-compute-0-exec-start.sh
root      1364  0.0  2.0 826280 82196 ?        Sl   Feb17   0:38 /var/lib/juju/tools/unit-nova-compute-0/jujud unit --data-dir /var/lib/juju --unit-name nova-compute/0 --debug
nova      1724  0.3  4.1 1792016 167760 ?      Ssl  Feb17   6:14 /usr/bin/python3 /usr/bin/nova-compute --config-file=/etc/nova/nova.conf --config-file=/etc/nova/nova-compute.conf --log-file=/var/log/nova/nova-compute.log
root      3622  0.9  2.4 304912 97632 ?        S    Feb17  15:13 /usr/bin/python3 /usr/bin/neutron-ovn-metadata-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/neutron_ovn_metadata_agent.ini --log-file=/var/log/neutron/neutron-ovn-metadata-agent.log
root      3623  0.9  2.4 304780 97532 ?        S    Feb17  15:05 /usr/bin/python3 /usr/bin/neutron-ovn-metadata-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/neutron_ovn_metadata_agent.ini --log-file=/var/log/neutron/neutron-ovn-metadata-agent.log
root      3633  0.0  1.8 400716 75576 ?        Sl   Feb17   0:00 /usr/bin/python3 /usr/bin/privsep-helper --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/neutron_ovn_metadata_agent.ini --privsep_context neutron.privileged.default --privsep_sock_path /tmp/tmpxkxj1yiy/privsep.sock
root      6900  0.0  1.1 371148 48164 ?        Sl   Feb17   0:00 /usr/bin/python3 /usr/bin/privsep-helper --config-file /etc/nova/nova.conf --config-file /etc/nova/nova-compute.conf --privsep_context vif_plug_ovs.privsep.vif_plug --privsep_sock_path /tmp/tmprgcsxyri/privsep.sock
nova      7336  0.0  2.4 296092 99488 ?        S    Feb17   0:07 /usr/bin/python3 /usr/bin/nova-api-metadata --config-file=/etc/nova/nova.conf --log-file=/var/log/nova/nova-api-metadata.log
nova      7337  0.0  2.4 295964 99484 ?        S    Feb17   0:07 /usr/bin/python3 /usr/bin/nova-api-metadata --config-file=/etc/nova/nova.conf --log-file=/var/log/nova/nova-api-metadata.log
nova      7338  0.0  2.4 296092 99484 ?        S    Feb17   0:07 /usr/bin/python3 /usr/bin/nova-api-metadata --config-file=/etc/nova/nova.conf --log-file=/var/log/nova/nova-api-metadata.log
nova      7339  0.0  2.4 295960 99492 ?        S    Feb17   0:06 /usr/bin/python3 /usr/bin/nova-api-metadata --config-file=/etc/nova/nova.conf --log-file=/var/log/nova/nova-api-metadata.log
libvirt+ 26860  0.1 20.7 3461772 837468 ?      Sl   Feb17   2:18 /usr/bin/qemu-system-x86_64 -name guest=instance-00000002,debug-threads=on -S -object secret,id=masterKey0,format=raw,file=/var/lib/libvirt/qemu/domain-1-instance-00000002/master-key.aes -machine pc-i440fx-4.2,accel=kvm,usb=off,dump-guest-core=off -cpu Haswell-noTSX-IBRS,vme=on,ss=on,vmx=on,f16c=on,rdrand=on,hypervisor=on,arat=on,tsc-adjust=on,md-clear=on,ssbd=on,xsaveopt=on,pdpe1gb=on,abm=on -m 2048 -overcommit mem-lock=off -smp 1,sockets=1,cores=1,threads=1 -uuid 09461f0b-297b-4ef5-9053-dd369c86b96b -smbios type=1,manufacturer=OpenStack Foundation,product=OpenStack Nova,version=21.1.0,serial=09461f0b-297b-4ef5-9053-dd369c86b96b,uuid=09461f0b-297b-4ef5-9053-dd369c86b96b,family=Virtual Machine -display none -no-user-config -nodefaults -chardev socket,id=charmonitor,fd=31,server,nowait -mon chardev=charmonitor,id=monitor,mode=control -rtc base=utc,driftfix=slew -global kvm-pit.lost_tick_policy=delay -no-hpet -no-shutdown -boot strict=on -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -blockdev {"driver":"file","filename":"/var/lib/nova/instances/_base/577f900655f2d3c964fd25d4982d61907ea39508","node-name":"libvirt-2-storage","cache":{"direct":true,"no-flush":false},"auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-2-format","read-only":true,"discard":"unmap","cache":{"direct":true,"no-flush":false},"driver":"qcow2","file":"libvirt-2-storage","backing":null} -blockdev {"driver":"file","filename":"/var/lib/nova/instances/09461f0b-297b-4ef5-9053-dd369c86b96b/disk","node-name":"libvirt-1-storage","cache":{"direct":true,"no-flush":false},"auto-read-only":true,"discard":"unmap"} -blockdev {"node-name":"libvirt-1-format","read-only":false,"discard":"unmap","cache":{"direct":true,"no-flush":false},"driver":"qcow2","file":"libvirt-1-storage","backing":"libvirt-2-format"} -device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x3,drive=libvirt-1-format,id=virtio-disk0,bootindex=1,write-cache=on -netdev tap,fd=33,id=hostnet0,vhost=on,vhostfd=34 -device virtio-net-pci,host_mtu=1492,netdev=hostnet0,id=net0,mac=fa:16:3e:02:20:bb,bus=pci.0,addr=0x2 -add-fd set=3,fd=36 -chardev pty,id=charserial0,logfile=/dev/fdset/3,logappend=on -device isa-serial,chardev=charserial0,id=serial0 -device virtio-balloon-pci,id=balloon0,bus=pci.0,addr=0x4 -object rng-random,id=objrng0,filename=/dev/urandom -device virtio-rng-pci,rng=objrng0,id=rng0,bus=pci.0,addr=0x5 -sandbox on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny -msg timestamp=on
root     26938  0.0  0.0  54128  1148 ?        Ss   Feb17   0:02 haproxy -f /var/lib/neutron/ovn-metadata-proxy/f1f53874-52db-4f62-895b-f3db0688e99d.conf
root     27208  0.0  0.9 285060 37848 ?        Sl   Feb17   0:00 /usr/bin/python3 /usr/bin/privsep-helper --config-file /etc/nova/nova.conf --config-file /etc/nova/nova-compute.conf --privsep_context nova.privsep.sys_admin_pctxt --privsep_sock_path /tmp/tmp8jc4btoe/privsep.sock
"""  # noqa

APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
debug = True
"""


def fake_ip_link_show_w_errors_drops():
    return [line + '\n' for line in IP_LINK_SHOW.format(10000000,
                                                        100000000).split('\n')]


def fake_ip_link_show_no_errors_drops():
    return [line + '\n' for line in IP_LINK_SHOW.format(0, 0).split('\n')]


def fake_ip_addr_show():
    return [line + '\n' for line in IP_ADDR_SHOW.split('\n')]


def fake_ps():
    return [line + '\n' for line in PS.split('\n')]


class TestOpenstackPlugin01openstack(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    @mock.patch.object(ost_01openstack.helpers, 'get_ps', fake_ps)
    def test_get_service_info(self):
        result = {'services': ['haproxy (1)',
                               'neutron-ovn-metadata-agent (3)',
                               'nova-api-metadata (5)',
                               'nova-compute (1)',
                               'qemu-system-x86_64 (1)']}
        ost_01openstack.get_service_info()
        self.assertEqual(ost_01openstack.OPENSTACK_INFO, result)

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch.object(ost_01openstack, "APT_SOURCE_PATH", dtmp):
                ost_01openstack.get_release_info()
                self.assertEqual(ost_01openstack.OPENSTACK_INFO,
                                 {"release": "ussuri"})

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    def test_get_debug_log_info(self):
        result = {'debug-logging-enabled': {'neutron': True, 'nova': True}}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            with mock.patch.object(ost_01openstack, "DATA_ROOT", dtmp):
                ost_01openstack.get_debug_log_info()
                self.assertEqual(ost_01openstack.OPENSTACK_INFO, result)


class TestOpenstackPlugin02vm_info(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_02vm_info, "VM_INFO", [])
    @mock.patch.object(ost_01openstack.helpers, 'get_ps', fake_ps)
    def test_get_vm_info(self):
        ost_02vm_info.get_vm_info()
        self.assertEquals(ost_02vm_info.VM_INFO,
                          ["09461f0b-297b-4ef5-9053-dd369c86b96b"])


class TestOpenstackPlugin03nova_external_events(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin04package_versions(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin05network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_name(self):
        stats = ost_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {'dropped': '100000000 (8%)'})

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_no_errors_drops)
    def test_get_port_stat_by_name_no_problems(self):
        stats = ost_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {})

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_mac(self):
        stats = ost_05network.get_port_stats(mac="ac:1f:6b:9e:d8:44")
        self.assertEqual(stats, {'errors': '10000000 (5%)'})

    @mock.patch.object(ost_05network.helpers, 'get_ip_addr',
                       fake_ip_addr_show)
    def test_find_interface_name_by_ip_address(self):
        addr = "10.10.101.33"
        name = ost_05network.find_interface_name_by_ip_address(addr)
        self.assertEqual(name, "br-bond1")


class TestOpenstackPlugin06_service_features(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin07_cpu_pinning_check(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()
