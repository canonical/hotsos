import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

# need this for non-standard import
spec = spec_from_loader("openstack_05network",
                        SourceFileLoader("openstack_05network",
                                         "plugins/openstack/05network"))
openstack_05network = module_from_spec(spec)
spec.loader.exec_module(openstack_05network)


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


def fake_ip_link_show_w_errors_drops():
    return [line + '\n' for line in IP_LINK_SHOW.format(10000000,
                                                        100000000).split('\n')]


def fake_ip_link_show_no_errors_drops():
    return [line + '\n' for line in IP_LINK_SHOW.format(0, 0).split('\n')]


def fake_ip_addr_show():
    return [line + '\n' for line in IP_ADDR_SHOW.split('\n')]


class TestOpenstack(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(openstack_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_name(self):
        stats = openstack_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {'dropped': '100000000 (8%)'})

    @mock.patch.object(openstack_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_no_errors_drops)
    def test_get_port_stat_by_name_no_problems(self):
        stats = openstack_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {})

    @mock.patch.object(openstack_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_mac(self):
        stats = openstack_05network.get_port_stats(mac="ac:1f:6b:9e:d8:44")
        self.assertEqual(stats, {'errors': '10000000 (5%)'})

    @mock.patch.object(openstack_05network.helpers, 'get_ip_addr',
                       fake_ip_addr_show)
    def test_find_interface_name_by_ip_address(self):
        addr = "10.10.101.33"
        name = openstack_05network.find_interface_name_by_ip_address(addr)
        self.assertEqual(name, "br-bond1")
