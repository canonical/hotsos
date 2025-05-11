from unittest import mock

from hotsos.core.host_helpers import cli
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.kernel import CallTraceManager
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel.memory import (
    BuddyInfo,
    SlabInfo,
    MallocInfo,
)
from hotsos.core.plugins.kernel.net import SockStat, NetLink, Lsof
from hotsos.plugin_extensions.kernel import summary

from . import utils

PROC_SOCKSTAT = r"""sockets: used 908
TCP: inuse 22 orphan 0 tw 2 alloc 58 mem 150987
UDP: inuse 18 mem 350876
UDPLITE: inuse 44
RAW: inuse 55
FRAG: inuse 66 memory 77
"""  # noqa, pylint: disable=C0301

PROC_SOCKSTAT_BAD = r"""sockets: used 908
TCP: inuse 22 orphan 0 tw 2 alloc 58 mem 15
UDP: inuse 18 mem 350876
UDPLITE: inuse 44
UNKNOWN: inuse 22 orphan 15
CORRUPT: inuse orphan 15
RAW: inuse 55
FRAG: inuse 66 memory 77
"""  # noqa, pylint: disable=C0301

PROC_SOCKSTAT_SYSCTL_A = r"""
net.ipv4.udp_mem = 379728	506307	762456
net.ipv4.tcp_mem = 189864	253153	379728
"""

# pylint: disable=C0301
PROC_NETLINK = r"""sk               Eth Pid        Groups   Rmem     Wmem     Dump  Locks    Drops    Inode
0000000000000000 0   23984      00000113 0        0        0     2        0        129906  
0000000000000000 0   142171     00000113 0        0        0     2        0        411370  
0000000000000000 0   12686      00000440 0        0        0     2        0        112920  
0000000000000000 0   186014     00000113 0        0        0     2        0        636924  
0000000000000000 0   186159     00000113 0        0        0     2        0        610163  
0000000000000000 0   10132      00000440 0        0        0     2        0        108883  
0000000000000000 0   2719       00000550 0        0        0     2        0        90600   
0000000000000000 0   10542      00000113 0        0        0     2        0        114127  
0000000000000000 0   2199       000405d1 0        0        0     2        1        34703   
0000000000000000 0   3426       00000440 0        0        0     2        0        89397 
"""  # noqa

# pylint: disable=C0301
LSOF_MNLC = r"""                                                                                                                                                                                                                                    COMMAND     PID   USER   FD      TYPE             DEVICE     SIZE/OFF       NODE NAME
systemd       1        0  cwd       DIR                9,1         4096          2 /
systemd       1        0  rtd       DIR                9,1         4096          2 /
systemd       1        0  txt       REG                9,1      1589552      54275 /lib/systemd/systemd
ksoftirqd   180        0  rtd       DIR                9,1         4096          2 /
watchdog/   382        0  rtd       DIR                9,1         4096          2 /
kswapd0     590        0  rtd       DIR                9,1         4096          2 /
rsyslogd   4084        0  mem       REG                9,1        18976      51133 /lib/x86_64-linux-gnu/libuuid.so.1.3.0
ceilomete  4129      116  mem       REG                9,1        43200      48271 /usr/lib/x86_64-linux-gnu/libyajl.so.2.1.0
kworker/1 10645        0  rtd       DIR                9,1         4096          2 /
ovs-vswit 13936        0  mem-R     REG               0,43      2097152     129906 /mnt/huge_ovs_2M/rtemap_286
ovs-vswit 13936        0  mem-R     REG               0,43      2097152      44403 /mnt/huge_ovs_2M/rtemap_33226
ovs-vswit 13936        0   16u  a_inode               0,13            0      11305 [timerfd]
ovs-vswit 13936        0  616uR     REG               0,43      2097152      34703 /mnt/huge_ovs_2M/rtemap_586
eal-intr- 13936        0  mem-R     REG               0,43      2097152      43181 /mnt/huge_ovs_2M/rtemap_260
eal-intr- 13936        0  mem       REG                9,1      1088952      31573 /lib/x86_64-linux-gnu/libm-2.23.so
eal-intr- 13936        0 1790uR     REG               0,43      2097152      44681 /mnt/huge_ovs_2M/rtemap_33504
rte_mp_ha 13936        0  mem-R     REG               0,43      2097152      43155 /mnt/huge_ovs_2M/rtemap_234
dpdk_watc 13936        0  mem-R     REG               0,43      2097152      43129 /mnt/huge_ovs_2M/rtemap_208
ct_clean4 13936        0  mem-R     REG               0,43      2097152      43103 /mnt/huge_ovs_2M/rtemap_182
ipf_clean 13936        0  mem-R     REG               0,43      2097152      43077 /mnt/huge_ovs_2M/rtemap_156
urcu3     13936        0  mem-R     REG               0,43      2097152      43051 /mnt/huge_ovs_2M/rtemap_130
urcu3     13936        0 1660uR     REG               0,43      2097152      44551 /mnt/huge_ovs_2M/rtemap_33374
pmd7      13936        0  mem-R     REG               0,43      2097152      43025 /mnt/huge_ovs_2M/rtemap_104
pmd8      13936        0  mem-R     REG               0,43      2097152      39927 /mnt/huge_ovs_2M/rtemap_78
pmd8      13936        0 1608uR     REG               0,43      2097152      44499 /mnt/huge_ovs_2M/rtemap_33322
pmd9      13936        0  mem-R     REG               0,43      2097152      39901 /mnt/huge_ovs_2M/rtemap_52
pmd9      13936        0 1582uR     REG               0,43      2097152      44473 /mnt/huge_ovs_2M/rtemap_33296
pmd10     13936        0  mem-R     REG               0,43      2097152      39875 /mnt/huge_ovs_2M/rtemap_26
vhost_rec 13936        0  mem-R     REG               0,43      2097152      39849 /mnt/huge_ovs_2M/rtemap_0
vhost_rec 13936        0 1530uR     REG               0,43      2097152      44421 /mnt/huge_ovs_2M/rtemap_33244
vhost_rec 13936        0 2130r     FIFO               0,12          0t0      41344 pipe
vhost-eve 13936        0  mem-R     REG               0,43      2097152      43495 /mnt/huge_ovs_2M/rtemap_574
vhost-eve 13936        0 2104u      CHR             10,200          0t0        136 /dev/net/tun
monitor13 13936        0  mem-R     REG               0,43      2097152     411370 /mnt/huge_ovs_2M/rtemap_548
monitor13 13936        0 2078u  a_inode               0,13            0      11305 [vfio-device]
revalidat 13936        0  mem-R     REG               0,43      2097152      43417 /mnt/huge_ovs_2M/rtemap_496
zabbix_ag 17684      111  cwd       DIR                9,1         4096          2 /
zabbix_ag 17712      111  mem       REG                9,1       219240      33580 /usr/lib/x86_64-linux-gnu/libnettle.so.6.3
ceilomete 18072      116   48w     FIFO               0,12          0t0      81191 pipe
ceilomete 18072      116  114w     FIFO               0,12          0t0      81243 pipe
qemu-syst 20986        0   44u  a_inode               0,13            0      34703 [eventfd]
CPU\x201/ 20986        0  mem       REG                9,1        43648      49833 /usr/lib/x86_64-linux-gnu/libcacard.so.0.0.0
CPU\x2028 20986        0   74u  a_inode               0,13            0      11305 kvm-vcpu
CPU\x2031 20986        0   17u  a_inode               0,13            0      11305 kvm-vm
agetty    23623        0  rtd       DIR                9,1         4096          2 /
libvirtd  44443        0   25u     unix 0xffffa01631378000          0t0    2022202 /var/run/libvirt/libvirt-sock-ro type=STREAM
libvirtd  44443        0  mem       REG                9,1       408472      33585 /usr/lib/x86_64-linux-gnu/libp11-kit.so.0.1.0
nova-comp 49287      114  mem       REG                9,1        68512      33561 /usr/lib/x86_64-linux-gnu/libavahi-client.so.3.2.9
nova-comp 49287      114   21u     IPv4            2914832          0t0        TCP 192.168.2.24:46064->192.168.2.45:5673 (ESTABLISHED)
sosreport 67605        0    5r     FIFO               0,12          0t0  289262208 pipe
"""  # noqa

KERNLOG_OOM_KILL = """
# this is a simulated oom kill for the unit tests
[27742.909073] kworker/0:0 invoked oom-killer: gfp_mask=0xcc0(GFP_KERNEL), order=-1, oom_score_adj=0
[27742.909076] CPU: 0 PID: 17681 Comm: kworker/0:0 Not tainted 5.4.0-120-generic #136-Ubuntu
[27742.909077] Hardware name: QEMU Standard PC (i440FX + PIIX, 1996), BIOS 1.15.0-1 04/01/2014
[27742.909094] Workqueue: events moom_callback
[27742.909097] Call Trace:
[27742.909114]  dump_stack+0x6d/0x8b
[27742.909120]  dump_header+0x4f/0x1eb
[27742.909121]  oom_kill_process.cold+0xb/0x10
[27742.909129]  out_of_memory+0x1cf/0x4d0
[27742.909130]  moom_callback+0x7d/0xb0
[27742.909135]  process_one_work+0x1eb/0x3b0
[27742.909137]  worker_thread+0x4d/0x400
[27742.909138]  kthread+0x104/0x140
[27742.909139]  ? process_one_work+0x3b0/0x3b0
[27742.909139]  ? kthread_park+0x90/0x90
[27742.909142]  ret_from_fork+0x35/0x40
[27742.909142] Mem-Info:
[27742.909146] active_anon:416825 inactive_anon:1538 isolated_anon:0
                active_file:140909 inactive_file:149407 isolated_file:0
                unevictable:4659 dirty:375 writeback:0 unstable:0
                slab_reclaimable:21193 slab_unreclaimable:19283
                mapped:78827 shmem:9373 pagetables:4336 bounce:0
                free:227215 free_pcp:587 free_cma:0
[27742.909147] Node 0 active_anon:1667300kB inactive_anon:6152kB active_file:563636kB inactive_file:597628kB unevictable:18636kB isolated(anon):0kB isolated(file):0kB mapped:315308kB dirty:1500kB writeback:0kB shmem:37492kB shmem_thp: 0kB shmem_pmdmapped: 0kB anon_thp: 0kB>
[27742.909148] Node 0 DMA free:15908kB min:268kB low:332kB high:396kB active_anon:0kB inactive_anon:0kB active_file:0kB inactive_file:0kB unevictable:0kB writepending:0kB present:15992kB managed:15908kB mlocked:0kB kernel_stack:0kB pagetables:0kB bounce:0kB free_pcp:0kB lo>
[27742.909149] lowmem_reserve[]: 0 2929 3882 3882 3882
[27742.909150] Node 0 DMA32 free:872388kB min:50784kB low:63480kB high:76176kB active_anon:1423716kB inactive_anon:4096kB active_file:350532kB inactive_file:269332kB unevictable:0kB writepending:568kB present:3129184kB managed:3034312kB mlocked:0kB kernel_stack:2432kB page>
[27742.909152] lowmem_reserve[]: 0 0 953 953 953
[27742.909152] Node 0 Normal free:20564kB min:16524kB low:20652kB high:24780kB active_anon:243584kB inactive_anon:2056kB active_file:213104kB inactive_file:328296kB unevictable:18636kB writepending:932kB present:1048576kB managed:976040kB mlocked:18636kB kernel_stack:4192k>
[27742.909164] lowmem_reserve[]: 0 0 0 0 0
[27742.909165] Node 0 DMA: 1*4kB (U) 0*8kB 0*16kB 1*32kB (U) 2*64kB (U) 1*128kB (U) 1*256kB (U) 0*512kB 1*1024kB (U) 1*2048kB (M) 3*4096kB (M) = 15908kB
[27742.909168] Node 0 DMA32: 1004*4kB (UM) 1552*8kB (UME) 752*16kB (UME) 404*32kB (UME) 133*64kB (UME) 58*128kB (UME) 36*256kB (UME) 28*512kB (UM) 11*1024kB (M) 9*2048kB (UM) 186*4096kB (M) = 872432kB
[27742.909171] Node 0 Normal: 489*4kB (UE) 250*8kB (U) 114*16kB (UME) 66*32kB (UME) 16*64kB (UE) 11*128kB (UME) 6*256kB (U) 3*512kB (UME) 1*1024kB (E) 3*2048kB (UME) 0*4096kB = 20564kB
[27742.909179] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=1048576kB
[27742.909184] Node 0 hugepages_total=0 hugepages_free=0 hugepages_surp=0 hugepages_size=2048kB
[27742.909184] 300582 total pagecache pages
[27742.909185] 0 pages in swap cache
[27742.909185] Swap cache stats: add 0, delete 0, find 0/0
[27742.909185] Free swap  = 0kB
[27742.909186] Total swap = 0kB
[27742.909186] 1048438 pages RAM
[27742.909186] 0 pages HighMem/MovableOnly
[27742.909187] 41873 pages reserved
[27742.909187] 0 pages cma reserved
[27742.909187] 0 pages hwpoisoned
[27742.909188] Tasks state (memory values in pages):
[27742.909188] [  pid  ]   uid  tgid total_vm      rss pgtables_bytes swapents oom_score_adj name
[27742.909192] [    341]     0   341    17174     6831   135168        0          -250 systemd-journal
[27742.909194] [    368]     0   368     5257     1613    69632        0         -1000 systemd-udevd
[27742.909196] [    500]     0   500    70049     4499    94208        0         -1000 multipathd
[27742.909198] [    572]   102   572    22724     1509    81920        0             0 systemd-timesyn
[27742.909199] [    680]   100   680     6846     1957    73728        0             0 systemd-network
[27742.909200] [    682]   101   682     6134     3313    86016        0             0 systemd-resolve
[27742.909201] [    715]     0   715    59520     2067    94208        0             0 accounts-daemon
[27742.909202] [    716]   117   716     2151      875    49152        0             0 avahi-daemon
[27742.909203] [    717]   103   717     2156     1373    53248        0          -900 dbus-daemon
[27742.909203] [    718]     0   718    65316     4831   151552        0             0 NetworkManager
[27742.909204] [    723]     0   723     9279     5100   102400        0             0 networkd-dispat
[27742.909205] [    724]     0   724    58750     2378    90112        0             0 polkitd
[27742.909206] [    726]   104   726    56086     1266    77824        0             0 rsyslogd
[27742.909207] [    727]     0   727   181712     9955   229376        0          -900 snapd
[27742.909208] [    728]     0   728    58682     1488    81920        0             0 switcheroo-cont
[27742.909209] [    729]     0   729     4351     2127    69632        0             0 systemd-logind
[27742.909210] [    730]     0   730    98322     3049   131072        0             0 udisksd
[27742.909211] [    731]     0   731     3419     1269    61440        0             0 wpa_supplicant
[27742.909211] [    737]   117   737     2085       80    49152        0             0 avahi-daemon
[27742.909212] [    769]     0   769    78611     2703   110592        0             0 ModemManager
[27742.909213] [    785]     0   785     5032      866    77824        0             0 postgres.wrappe
[27742.909214] [    786]     0   786     7381     6241    94208        0             0 python3
[27742.909215] [    819]     0   819    28933     5670   122880        0             0 unattended-upgr
[27742.909216] [    840]     0   840     2134      748    49152        0             0 cron
[27742.909217] [    846]     0   846      948      566    40960        0             0 atd
[27742.909223] [    849]     0   849      622      143    40960        0             0 none
[27742.909224] [    856]     0   856     1838      569    45056        0             0 agetty
[27742.909225] [    865]     0   865     3043     1854    61440        0         -1000 sshd
[27742.909225] [    866]     0   866    59656     2126    94208        0             0 gdm3
[27742.909226] [    879]     0   879    41481     2283    90112        0             0 gdm-session-wor
[27742.909227] [    884]   121   884     4823     2515    81920        0             0 systemd
[27742.909228] [    887]   121   887    26042      893    86016        0             0 (sd-pam)
[27742.909228] [    897]   121   897   200967     3621   151552        0             0 pulseaudio
[27742.909229] [    900]   121   900    40198     1373    77824        0             0 gdm-wayland-ses
[27742.909230] [    906]   121   906     1776     1026    57344        0             0 dbus-daemon
[27742.909231] [    911]   121   911     1322      275    49152        0             0 dbus-run-sessio
[27742.909231] [    912]   121   912     1886     1169    49152        0             0 dbus-daemon
[27742.909232] [    913]   121   913   120596     3604   155648        0             0 gnome-session-b
[27742.909233] [    914]   112   914    38232      736    65536        0             0 rtkit-daemon
[27742.909234] [    955]   121   955   822385    46313   806912        0             0 gnome-shell
[27742.909235] [    992]   121   992    76318     1611    90112        0             0 at-spi-bus-laun
[27742.909236] [    997]   121   997     1776      999    57344        0             0 dbus-daemon
[27742.909237] [   1005]   121  1005    36965    11864   294912        0             0 Xwayland
[27742.909237] [   1013] 584788  1013    58452     5634   188416        0             0 postgres
[27742.909239] [   1052]     0  1052    62816     2424   110592        0             0 upowerd
[27742.909239] [   1064]   121  1064   649270     6449   217088        0             0 gjs
[27742.909240] [   1065]   121  1065    40690     1736    86016        0             0 at-spi2-registr
[27742.909241] [   1072]   121  1072   121470     5476   172032        0             0 gsd-color
[27742.909241] [   1073]   121  1073    80244     2684   118784        0             0 gsd-print-notif
[27742.909242] [   1075]   121  1075    77174     1591    94208        0             0 gsd-a11y-settin
[27742.909243] [   1078]   121  1078   121350     5469   172032        0             0 gsd-power
[27742.909244] [   1079]   121  1079   151442     5671   172032        0             0 gsd-media-keys
[27742.909244] [   1080]   121  1080   114061     1464   106496        0             0 gsd-rfkill
[27742.909245] [   1082]   121  1082    84246     5203   155648        0             0 gsd-keyboard
[27742.909246] [   1083]   121  1083    84160     5146   159744        0             0 gsd-wacom
[27742.909247] [   1084]   121  1084    77568     1857   102400        0             0 gsd-housekeepin
[27742.909247] [   1086]   121  1086    79475     2247   110592        0             0 gsd-sound
[27742.909248] [   1088]   121  1088    93164     4021   155648        0             0 gsd-datetime
[27742.909249] [   1089]   121  1089    78549     2442   114688        0             0 gsd-smartcard
[27742.909250] [   1093]   121  1093    58663     1436    90112        0             0 gsd-screensaver
[27742.909250] [   1095]   121  1095   115922     2492   114688        0             0 gsd-sharing
[27742.909251] [   1110]   121  1110    85333     3721   147456        0             0 gsd-printer
[27742.909252] [   1225]   120  1225    61204     3514   106496        0             0 colord
[27742.909253] [   1244]   121  1244    95819     1940    94208        0             0 ibus-daemon
[27742.909254] [   1253]   121  1253    40307     1519    81920        0             0 ibus-memconf
[27742.909254] [   1256]   121  1256    78495    13100   352256        0             0 ibus-x11
[27742.909259] [   1262] 584788  1262    58492     4205   188416        0             0 postgres
[27742.909260] [   1263] 584788  1263    58452     1869   155648        0             0 postgres
[27742.909261] [   1264] 584788  1264    58452     2076   147456        0             0 postgres
[27742.909262] [   1265] 584788  1265    58555     1642   155648        0             0 postgres
[27742.909262] [   1266] 584788  1266    22250      935   131072        0             0 postgres
[27742.909263] [   1267]   121  1267    58757     1543    86016        0             0 ibus-portal
[27742.909264] [   1276]   121  1276    40338     1540    81920        0             0 ibus-engine-sim
[27742.909265] [   1277] 584788  1277    58525     1069   147456        0             0 postgres
[27742.909266] [   1306]     0  1306    54044     8492   147456        0             0 named
[27742.909267] [   1311]     0  1311   123030    21755   278528        0             0 python3
[27742.909268] [   1312]     0  1312   185516    28024   360448        0             0 python3
[27742.909268] [   1343]     0  1343    14821    13522   151552        0             0 python3
[27742.909269] [   1344]     0  1344    14821    13520   151552        0             0 python3
[27742.909270] [   1345]     0  1345    14810    13520   155648        0             0 python3
[27742.909271] [   1346]     0  1346    14821    13563   155648        0             0 python3
[27742.909272] [   1347]     0  1347    14810    13562   151552        0             0 python3
[27742.909272] [   1348]     0  1348    14810    13528   151552        0             0 python3
[27742.909273] [   1349]     0  1349    14810    13523   163840        0             0 python3
[27742.909274] [   1350]   107  1350     2436      251    61440        0             0 uuidd
[27742.909275] [   1359] 584788  1359    59519     5720   217088        0             0 postgres
[27742.909275] [   1368] 584788  1368    60177     6547   225280        0             0 postgres
[27742.909276] [   1371] 584788  1371    58682     2518   159744        0             0 postgres
[27742.909277] [   1373] 584788  1373    59863     5894   221184        0             0 postgres
[27742.909278] [   1375] 584788  1375    59628     5611   225280        0             0 postgres
[27742.909278] [   1377] 584788  1377    59836     6100   225280        0             0 postgres
[27742.909279] [   1381]     0  1381   191747    35554   409600        0             0 python3
[27742.909280] [   1382]     0  1382   191011    35133   417792        0             0 python3
[27742.909280] [   1383]     0  1383   133690    32391   372736        0             0 python3
[27742.909281] [   1384] 584788  1384    60380     6818   229376        0             0 postgres
[27742.909282] [   1385]     0  1385   191285    35687   421888        0             0 python3
[27742.909283] [   1399]     0  1399    19707      769    53248        0             0 chronyd
[27742.909283] [   1401]     0  1401    77644     1052   110592        0             0 rsyslogd
[27742.909284] [   1416]     0  1416     3120     1954    61440        0             0 tcpdump
[27742.909285] [   1417]     0  1417     3120     1973    65536        0             0 tcpdump
[27742.909286] [   1418]     0  1418     3120     1940    65536        0             0 tcpdump
[27742.909287] [   1419]     0  1419     3120     1932    61440        0             0 tcpdump
[27742.909287] [   1420]     0  1420     3120     1962    69632        0             0 tcpdump
[27742.909288] [   1421]     0  1421     3120     1976    65536        0             0 tcpdump
[27742.909289] [   1422]     0  1422     3120     1981    69632        0             0 tcpdump
[27742.909289] [   1462] 584788  1462    58683     2520   159744        0             0 postgres
[27742.909290] [   1469] 584788  1469    58683     2505   159744        0             0 postgres
[27742.909291] [   1471] 584788  1471    58683     2520   159744        0             0 postgres
[27742.909295] [   1483] 584788  1483    58683     2520   159744        0             0 postgres
[27742.909296] [   1542]     0  1542    14820    13520   155648        0             0 python3
[27742.909297] [   1543]     0  1543    14820    13536   155648        0             0 python3
[27742.909298] [   1544]     0  1544    14820    13530   155648        0             0 python3
[27742.909299] [   1545]     0  1545    14821    13523   155648        0             0 python3
[27742.909299] [   1546]     0  1546    14820    13538   159744        0             0 python3
[27742.909300] [   1547]     0  1547    14797    13524   151552        0             0 python3
[27742.909301] [   1548]     0  1548    14820    13536   151552        0             0 python3
[27742.909301] [   1549]     0  1549    14810    13526   155648        0             0 python3
[27742.909302] [   1550]     0  1550     3067     2112    65536        0             0 nginx
[27742.909303] [   1554]     0  1554     3153      705    61440        0             0 nginx
[27742.909304] [   1609]     0  1609     2648     1513    57344        0             0 tcpdump
[27742.909305] [   1610]     0  1610     2648     1514    61440        0             0 tcpdump
[27742.909305] [   1611]     0  1611     2648     1504    61440        0             0 tcpdump
[27742.909306] [   1612]     0  1612     2648     1461    57344        0             0 tcpdump
[27742.909307] [   1615]     0  1615     2648     1494    61440        0             0 tcpdump
[27742.909307] [   1616]     0  1616     1830      666    53248        0             0 avahi-browse
[27742.909308] [   1617]     0  1617     2648     1463    61440        0             0 tcpdump
[27742.909309] [   1618]     0  1618     2648     1490    57344        0             0 tcpdump
[27742.909310] [   1660]     0  1660    26011     2691    86016        0             0 dhcpd
[27742.909311] [ 123860] 584788 123860    59032     4565   180224        0             0 postgres
[27742.909312] [ 125372] 584788 125372    59004     4459   180224        0             0 postgres
[27742.909313] [ 126460] 584788 126460    59615     5664   196608        0             0 postgres
[27742.909313] [ 126601] 584788 126601    59610     5393   212992        0             0 postgres
[27742.909314] [ 126733] 584788 126733    58964     4401   180224        0             0 postgres
[27742.909315] [ 126948] 584788 126948    59377     5619   196608        0             0 postgres
[27742.909315] [ 126950] 584788 126950    59008     4804   192512        0             0 postgres
[27742.909316] [ 126955] 584788 126955    59830     5222   217088        0             0 postgres
[27742.909317] [ 127097] 584788 127097    58977     4774   192512        0             0 postgres
[27742.909317] [ 128380] 584788 128380    58910     3658   176128        0             0 postgres
[27742.909318] [ 128520] 584788 128520    58964     4425   180224        0             0 postgres
[27742.909319] [ 128652] 584788 128652    58964     4400   180224        0             0 postgres
[27742.909320] [ 128926] 584788 128926    58910     4061   176128        0             0 postgres
[27742.909320] [ 129066] 584788 129066    58910     4075   176128        0             0 postgres
[27742.909321] [ 129203] 584788 129203    59030     4483   180224        0             0 postgres
[27742.909322] [ 129341] 584788 129341    59030     4507   180224        0             0 postgres
[27742.909322] [ 129751] 584788 129751    58964     4399   180224        0             0 postgres
[27742.909323] [ 129757] 584788 129757    58720     3035   167936        0             0 postgres
[27742.909324] [ 129892] 584788 129892    58910     3658   176128        0             0 postgres
[27742.909324] [ 129903]     0 129903     3462     2203    69632        0             0 sshd
[27742.909325] [ 129923]  1000 129923     4826     2501    77824        0             0 systemd
[27742.909330] [ 129926]  1000 129926    26049      933    86016        0             0 (sd-pam)
[27742.909331] [ 129931]  1000 129931    69870     3583   147456        0             0 pulseaudio
[27742.909331] [ 129950]  1000 129950     1776     1029    53248        0             0 dbus-daemon
[27742.909332] [ 130030]  1000 130030     3496     1487    69632        0             0 sshd
[27742.909333] [ 130032]  1000 130032     2541     1299    61440        0             0 bash
[27742.909333] [ 130047]  1000 130047     1785      879    53248        0             0 tmux: client
[27742.909334] [ 130082]  1000 130082     2030     1113    53248        0             0 tmux: server
[27742.909335] [ 130085]  1000 130085     2577     1357    53248        0             0 bash
[27742.909335] [ 130681]     0 130681     7013     5938    94208        0             0 python3
[27742.909336] oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,global_oom,task_memcg=/user.slice/user-121.slice/session-c1.scope,task=gnome-shell,pid=955,uid=121
[27742.909353] Out of memory: Killed process 955 (gnome-shell) total-vm:3289540kB, anon-rss:77868kB, file-rss:107372kB, shmem-rss:12kB, UID:121 pgtables:788kB oom_score_adj:0
"""  # noqa


class TestKernelBase(utils.BaseTestCase):
    """ Custom base testcase that sets kernel plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'kernel'


class MockJournalBinFileCmdOOMKillKernLog(cli.cli.JournalctlBinFileCmd):
    """ Mock the journalctl command to return some oom kill content. """
    def __call__(self, *args, **kwargs):
        return cli.common.CmdOutput(KERNLOG_OOM_KILL)


class TestKernelCallTraceManager(TestKernelBase):
    """ Unit tests for kernlog trace manager. """
    def common_test_calltrace_manager_handler(self):
        for killer in CallTraceManager().oom_killer:
            self.assertEqual(killer.procname, 'kworker/0:0')
            self.assertEqual(killer.pid, '955')

        heuristics = CallTraceManager().oom_killer.heuristics
        # one per zone
        self.assertEqual(len(heuristics), 3)
        for h in heuristics:
            if h.zone == 'DMA':
                self.assertEqual(h(),
                                 ['Node 0 zone DMA free pages 15908 below min '
                                  '268'])
            elif h.zone == 'Normal':
                self.assertEqual(h(),
                                 ['Node 0 zone Normal free pages 20564 below '
                                  'low 20652'])
            else:
                self.assertEqual(h(), [])

    @utils.create_data_root({'var/log/kern.log': KERNLOG_OOM_KILL})
    def test_calltrace_manager_handler_kern_log(self):
        self.common_test_calltrace_manager_handler()

    @utils.create_data_root({'sos_commands/logs/journalctl_--no-pager':
                             KERNLOG_OOM_KILL})
    def test_calltrace_manager_handler_journal_file(self):
        self.common_test_calltrace_manager_handler()

    # Create empty data root and mock the journal
    @utils.create_data_root({'var/log/journal': 'content'})
    def test_calltrace_manager_handler_systemd_journal(self):
        with mock.patch.object(cli.cli, 'JournalctlBinFileCmd') as \
                mock_cmd:
            mock_cmd.return_value = MockJournalBinFileCmdOOMKillKernLog(
                                        'var/log/journal')
            self.common_test_calltrace_manager_handler()


class TestKernelInfo(TestKernelBase):
    """ Unit tests for kernel info. """
    @utils.create_data_root({'etc/systemd/system.conf':
                             ('[Manager]\n'
                              '#CPUAffinity=1 2\n'
                              'CPUAffinity=0-7,32-39\n')})
    def test_systemd_config_ranges(self):
        self.assertEqual(SystemdConfig().get('CPUAffinity'), '0-7,32-39')
        self.assertEqual(SystemdConfig().get('CPUAffinity',
                                             expand_to_list=True),
                         [0, 1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37,
                          38, 39])
        self.assertTrue(SystemdConfig().cpuaffinity_enabled)

    @utils.create_data_root({'etc/systemd/system.conf':
                             ('[Manager]\n'
                              '#CPUAffinity=1 2\n'
                              'CPUAffinity=0 1 2 3 8 9 10 11\n')})
    def test_systemd_config_expanded(self):
        self.assertEqual(SystemdConfig().get('CPUAffinity'),
                         '0 1 2 3 8 9 10 11')

    @mock.patch('hotsos.core.plugins.kernel.config.SystemdConfig.get',
                lambda *args, **kwargs: '0-7,32-39')
    def test_info(self):
        inst = summary.KernelSummary()
        expected = {'boot': 'ro',
                    'cpu': {'cpufreq-scaling-governor': 'unknown',
                            'model': 'intel core processor (skylake, ibrs)',
                            'smt': 'disabled', 'vendor': 'genuineintel'},
                    'systemd': {'CPUAffinity': '0-7,32-39'},
                    'version': '5.4.0-97-generic'}
        self.assertTrue(inst.is_runnable())
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestKernelMemoryInfo(TestKernelBase):
    """ Unit tests for kernel memory info. """
    def test_numa_nodes(self):
        ret = BuddyInfo().nodes
        expected = [0]
        self.assertEqual(ret, expected)

    def test_get_node_zones(self):
        ret = BuddyInfo().get_node_zones("DMA32", 0)
        expected = "Node 0, zone DMA32 1127 453 112 65 27 7 13 6 5 30 48"
        self.assertEqual(ret, expected)

    def test_mallocinfo(self):
        m = MallocInfo(0, "Normal")
        self.assertEqual(m.empty_order_tally, 19)
        self.assertEqual(m.high_order_seq, 2)
        bsizes = {10: 0,
                  9: 0,
                  8: 2,
                  7: 4,
                  6: 14,
                  5: 35,
                  4: 222,
                  3: 1135,
                  2: 316,
                  1: 101,
                  0: 145}
        self.assertEqual(m.block_sizes_available, bsizes)

    def test_slab_major_consumers(self):
        top5 = SlabInfo(filter_names=[r"\S*kmalloc"]).major_consumers
        expected = ['buffer_head (87540.6796875k)',
                    'anon_vma_chain (9068.0k)',
                    'radix_tree_node (50253.65625k)',
                    'Acpi-State (5175.703125k)',
                    'vmap_area (2700.0k)']
        self.assertEqual(top5, expected)


class TestKernelNetworkInfo(TestKernelBase):
    """ Unit tests for kernel networking info. """
    @utils.create_data_root(
        {'proc/net/sockstat': PROC_SOCKSTAT,
         'sos_commands/kernel/sysctl_-a': PROC_SOCKSTAT_SYSCTL_A}
    )
    def test_sockstat_parse(self):
        uut = SockStat()
        self.assertEqual(uut.NsTotalSocksInUse, 908)
        self.assertEqual(uut.NsTcpSocksInUse, 22)
        self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
        self.assertEqual(uut.NsTcpSocksInTimeWait, 2)
        self.assertEqual(uut.GlobTcpSocksAllocated, 58)
        self.assertEqual(uut.GlobTcpSocksTotalMemPages, 150987)
        self.assertEqual(uut.NsUdpSocksInUse, 18)
        self.assertEqual(uut.GlobUdpSocksTotalMemPages, 350876)
        self.assertEqual(uut.NsUdpliteSocksInUse, 44)
        self.assertEqual(uut.NsRawSocksInUse, 55)
        self.assertEqual(uut.NsFragSocksInUse, 66)
        self.assertEqual(uut.NsFragSocksTotalMemPages, 77)
        self.assertEqual(uut.SysctlTcpMemMin, 189864)
        self.assertEqual(uut.SysctlTcpMemPressure, 253153)
        self.assertEqual(uut.SysctlTcpMemMax, 379728)
        self.assertEqual(uut.SysctlUdpMemMin, 379728)
        self.assertEqual(uut.SysctlUdpMemPressure, 506307)
        self.assertEqual(uut.SysctlUdpMemMax, 762456)
        self.assertEqual(int(uut.UDPMemUsagePct), 46)
        self.assertEqual(int(uut.TCPMemUsagePct), 39)

    @utils.create_data_root(
        {'proc/net/sockstat': PROC_SOCKSTAT_BAD,
         'sos_commands/kernel/sysctl_-a': PROC_SOCKSTAT_SYSCTL_A}
    )
    def test_sockstat_parse_bad(self):
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            uut = SockStat()
            self.assertEqual(uut.NsTotalSocksInUse, 908)
            self.assertEqual(uut.NsTcpSocksInUse, 22)
            self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
            self.assertEqual(uut.NsTcpSocksInTimeWait, 2)
            self.assertEqual(uut.GlobTcpSocksAllocated, 58)
            self.assertEqual(uut.GlobTcpSocksTotalMemPages, 15)
            self.assertEqual(uut.NsUdpSocksInUse, 18)
            self.assertEqual(uut.GlobUdpSocksTotalMemPages, 350876)
            self.assertEqual(uut.NsUdpliteSocksInUse, 44)
            self.assertEqual(uut.NsRawSocksInUse, 55)
            self.assertEqual(uut.NsFragSocksInUse, 66)
            self.assertEqual(uut.NsFragSocksTotalMemPages, 77)
            self.assertEqual(uut.SysctlTcpMemMin, 189864)
            self.assertEqual(uut.SysctlTcpMemPressure, 253153)
            self.assertEqual(uut.SysctlTcpMemMax, 379728)
            self.assertEqual(uut.SysctlUdpMemMin, 379728)
            self.assertEqual(uut.SysctlUdpMemPressure, 506307)
            self.assertEqual(int(uut.UDPMemUsagePct), 46)
            self.assertEqual(int(uut.TCPMemUsagePct), 0)
            # The CORRUPT line was invalid and log.warning() will be called
            self.assertEqual(len(log.output), 1)
            self.assertIn('failed to parse statistics for', log.output[0])

    @utils.create_data_root(
        {'proc/net/sockstat': "",
         'sos_commands/kernel/sysctl_-a': ""}
    )
    def test_sockstat_parse_sockstat_sysctl_absent(self):
        uut = SockStat()
        self.assertEqual(uut.NsTotalSocksInUse, 0)
        self.assertEqual(uut.NsTcpSocksInUse, 0)
        self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
        self.assertEqual(uut.NsTcpSocksInTimeWait, 0)
        self.assertEqual(uut.GlobTcpSocksAllocated, 0)
        self.assertEqual(uut.GlobTcpSocksTotalMemPages, 0)
        self.assertEqual(uut.NsUdpSocksInUse, 0)
        self.assertEqual(uut.GlobUdpSocksTotalMemPages, 0)
        self.assertEqual(uut.NsUdpliteSocksInUse, 0)
        self.assertEqual(uut.NsRawSocksInUse, 0)
        self.assertEqual(uut.NsFragSocksInUse, 0)
        self.assertEqual(uut.NsFragSocksTotalMemPages, 0)
        self.assertEqual(uut.SysctlTcpMemMin, 0)
        self.assertEqual(uut.SysctlTcpMemPressure, 0)
        self.assertEqual(uut.SysctlTcpMemMax, 0)
        self.assertEqual(uut.SysctlUdpMemMin, 0)
        self.assertEqual(uut.SysctlUdpMemPressure, 0)
        self.assertEqual(uut.UDPMemUsagePct, 0)
        self.assertEqual(uut.TCPMemUsagePct, 0)

    @utils.create_data_root(
        {'sos_commands/process/lsof_M_-n_-l_-c': LSOF_MNLC}
    )
    def test_lsof_parse(self):
        uut = Lsof()

        expected_output = [
            ("systemd", 1, 0, "cwd", "DIR", "9,1", "4096", 2, "/"),
            ("systemd", 1, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("systemd", 1, 0, "txt", "REG", "9,1", "1589552", 54275,
             "/lib/systemd/systemd"),
            ("ksoftirqd", 180, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("watchdog/", 382, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("kswapd0", 590, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("rsyslogd", 4084, 0, "mem", "REG", "9,1", "18976", 51133,
             "/lib/x86_64-linux-gnu/libuuid.so.1.3.0"),
            ("ceilomete", 4129, 116, "mem", "REG", "9,1", "43200", 48271,
             "/usr/lib/x86_64-linux-gnu/libyajl.so.2.1.0"),
            ("kworker/1", 10645, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("ovs-vswit", 13936, 0, "mem-R", "REG", "0,43", "2097152",
             129906, "/mnt/huge_ovs_2M/rtemap_286"),
            ("ovs-vswit", 13936, 0, "mem-R", "REG", "0,43", "2097152", 44403,
             "/mnt/huge_ovs_2M/rtemap_33226"),
            ("ovs-vswit", 13936, 0, "16u", "a_inode", "0,13", "0", 11305,
             "[timerfd]"),
            ("ovs-vswit", 13936, 0, "616uR", "REG", "0,43", "2097152", 34703,
             "/mnt/huge_ovs_2M/rtemap_586"),
            ("eal-intr-", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43181,
             "/mnt/huge_ovs_2M/rtemap_260"),
            ("eal-intr-", 13936, 0, "mem", "REG", "9,1", "1088952", 31573,
             "/lib/x86_64-linux-gnu/libm-2.23.so"),
            ("eal-intr-", 13936, 0, "1790uR", "REG", "0,43", "2097152", 44681,
             "/mnt/huge_ovs_2M/rtemap_33504"),
            ("rte_mp_ha", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43155,
             "/mnt/huge_ovs_2M/rtemap_234"),
            ("dpdk_watc", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43129,
             "/mnt/huge_ovs_2M/rtemap_208"),
            ("ct_clean4", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43103,
             "/mnt/huge_ovs_2M/rtemap_182"),
            ("ipf_clean", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43077,
             "/mnt/huge_ovs_2M/rtemap_156"),
            ("urcu3", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43051,
             "/mnt/huge_ovs_2M/rtemap_130"),
            ("urcu3", 13936, 0, "1660uR", "REG", "0,43", "2097152", 44551,
             "/mnt/huge_ovs_2M/rtemap_33374"),
            ("pmd7", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43025,
             "/mnt/huge_ovs_2M/rtemap_104"),
            ("pmd8", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39927,
             "/mnt/huge_ovs_2M/rtemap_78"),
            ("pmd8", 13936, 0, "1608uR", "REG", "0,43", "2097152", 44499,
             "/mnt/huge_ovs_2M/rtemap_33322"),
            ("pmd9", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39901,
             "/mnt/huge_ovs_2M/rtemap_52"),
            ("pmd9", 13936, 0, "1582uR", "REG", "0,43", "2097152", 44473,
             "/mnt/huge_ovs_2M/rtemap_33296"),
            ("pmd10", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39875,
             "/mnt/huge_ovs_2M/rtemap_26"),
            ("vhost_rec", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39849,
             "/mnt/huge_ovs_2M/rtemap_0"),
            ("vhost_rec", 13936, 0, "1530uR", "REG", "0,43", "2097152", 44421,
             "/mnt/huge_ovs_2M/rtemap_33244"),
            ("vhost_rec", 13936, 0, "2130r", "FIFO", "0,12", "0t0", 41344,
             "pipe"),
            ("vhost-eve", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43495,
             "/mnt/huge_ovs_2M/rtemap_574"),
            ("vhost-eve", 13936, 0, "2104u", "CHR", "10,200", "0t0", 136,
             "/dev/net/tun"),
            ("monitor13", 13936, 0, "mem-R", "REG", "0,43", "2097152", 411370,
             "/mnt/huge_ovs_2M/rtemap_548"),
            ("monitor13", 13936, 0, "2078u", "a_inode", "0,13", "0", 11305,
             "[vfio-device]"),
            ("revalidat", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43417,
             "/mnt/huge_ovs_2M/rtemap_496"),
            ("zabbix_ag", 17684, 111, "cwd", "DIR", "9,1", "4096", 2, "/"),
            ("zabbix_ag", 17712, 111, "mem", "REG", "9,1", "219240", 33580,
             "/usr/lib/x86_64-linux-gnu/libnettle.so.6.3"),
            ("ceilomete", 18072, 116, "48w", "FIFO", "0,12", "0t0", 81191,
             "pipe"),
            ("ceilomete", 18072, 116, "114w", "FIFO", "0,12", "0t0", 81243,
             "pipe"),
            ("qemu-syst", 20986, 0, "44u", "a_inode", "0,13", "0", 34703,
             "[eventfd]"),
            (r"CPU\x201/", 20986, 0, "mem", "REG", "9,1", "43648", 49833,
             "/usr/lib/x86_64-linux-gnu/libcacard.so.0.0.0"),
            (r"CPU\x2028", 20986, 0, "74u", "a_inode", "0,13", "0", 11305,
             "kvm-vcpu"),
            (r"CPU\x2031", 20986, 0, "17u", "a_inode", "0,13", "0", 11305,
             "kvm-vm"),
            ("agetty", 23623, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("libvirtd", 44443, 0, "25u", "unix", "0xffffa01631378000", "0t0",
             2022202, "/var/run/libvirt/libvirt-sock-ro type=STREAM"),
            ("libvirtd", 44443, 0, "mem", "REG", "9,1", "408472", 33585,
             "/usr/lib/x86_64-linux-gnu/libp11-kit.so.0.1.0"),
            ("nova-comp", 49287, 114, "mem", "REG", "9,1", "68512", 33561,
             "/usr/lib/x86_64-linux-gnu/libavahi-client.so.3.2.9"),
            ("nova-comp", 49287, 114, "21u", "IPv4", "2914832", "0t0",
             "TCP", "192.168.2.24:46064->192.168.2.45:5673 (ESTABLISHED)"),
            ("sosreport", 67605, 0, "5r", "FIFO", "0,12", "0t0", 289262208,
             "pipe"),
        ]

        self.assertEqual(len(uut.data), 50)

        for ridx, row in enumerate(uut.data):
            for fidx, fname in enumerate(uut.fields):
                self.assertEqual(getattr(row, fname),
                                 expected_output[ridx][fidx])

    @utils.create_data_root(
        {'proc/net/netlink': PROC_NETLINK}
    )
    def test_netlink_parse(self):
        uut = NetLink()

        expected_output = [
            (0, 0, 23984, 275, 0, 0, 0, 2, 0, 129906),
            (0, 0, 142171, 275, 0, 0, 0, 2, 0, 411370),
            (0, 0, 12686, 1088, 0, 0, 0, 2, 0, 112920),
            (0, 0, 186014, 275, 0, 0, 0, 2, 0, 636924),
            (0, 0, 186159, 275, 0, 0, 0, 2, 0, 610163),
            (0, 0, 10132, 1088, 0, 0, 0, 2, 0, 108883),
            (0, 0, 2719, 1360, 0, 0, 0, 2, 0, 90600),
            (0, 0, 10542, 275, 0, 0, 0, 2, 0, 114127),
            (0, 0, 2199, 263633, 0, 0, 0, 2, 1, 34703),
            (0, 0, 3426, 1088, 0, 0, 0, 2, 0, 89397),
        ]

        self.assertEqual(len(uut), 10)

        for ridx, row in enumerate(uut):
            for fidx, fname in enumerate(uut.fields):
                self.assertEqual(getattr(row, fname),
                                 expected_output[ridx][fidx])

    @utils.create_data_root(
        {'proc/net/netlink': PROC_NETLINK,
         'sos_commands/process/lsof_M_-n_-l_-c': LSOF_MNLC}
    )
    def test_netlink_parse_with_drops(self):
        uut = NetLink()
        awd = uut.all_with_drops
        self.assertEqual(len(awd), 1)
        self.assertEqual(awd[0].sk_addr, 0)
        self.assertEqual(awd[0].sk_protocol, 0)
        self.assertEqual(awd[0].netlink_port_id, 2199)
        self.assertEqual(awd[0].netlink_groups, 263633)
        self.assertEqual(awd[0].sk_rmem, 0)
        self.assertEqual(awd[0].sk_wmem, 0)
        self.assertEqual(awd[0].netlink_dump, 0)
        self.assertEqual(awd[0].sk_references, 2)
        self.assertEqual(awd[0].sk_drops, 1)
        self.assertEqual(awd[0].sk_inode_num, 34703)
        self.assertEqual(awd[0].procs, {'ovs-vswit/13936', 'qemu-syst/20986'})

    @utils.create_data_root(
        {'proc/net/netlink': PROC_NETLINK,
         'sos_commands/process/lsof_M_-n_-l_-c': LSOF_MNLC}
    )
    def test_netlink_parse_with_drops_str(self):
        uut = NetLink()
        awd = uut.all_with_drops_str
        self.assertEqual(awd,
                         "inode=34703 "
                         "procs=[ovs-vswit/13936, qemu-syst/20986]")


@utils.load_templated_tests('scenarios/kernel')
class TestKernelScenarios(TestKernelBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
