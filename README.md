# hotsos

Collect information about specific applications and raise issues when problems are detected. Can be run against a host or sosreport.

A number of application plugins are supported including Openstack, Ceph, Kubernetes, Juju and more. The standard output is structured YAML format.

By default all plugins are run and only produce ouput if applicable. If you want to run specific plugins you can choose from a selection (--list-plugins). See --help for more options.

### Usage

- Run hotsos against a sosreport (by default runs all plugins)

```
$ hotsos ./mysosreport
INFO: analysing sosreport at ./mysosreport
hotsos:
  version: development
  repo-info: 181b1e3
system:
  hostname: compute4
  os: ubuntu focal
  num-cpus: 2
  virtualisation: kvm
  unattended-upgrades: ENABLED
openstack:
  release: ussuri
  services:
    systemd:
      enabled:
        - haproxy
        - keepalived
        - neutron-dhcp-agent
        - neutron-l3-agent
        - neutron-metadata-agent
        - neutron-openvswitch-agent
        - neutron-ovs-cleanup
        - nova-compute
      masked:
        - nova-api-metadata
      disabled:
        - radvd
      indirect:
        - vaultlocker-decrypt
    ps:
      - apache2 (6)
      - dnsmasq (1)
      - glance-api (5)
      - haproxy (7)
      - keepalived (2)
      - mysqld (1)
      - neutron-dhcp-agent (1)
      - neutron-keepalived-state-change (2)
      - neutron-l3-agent (1)
      - neutron-metadata-agent (5)
      - neutron-openvswitch-agent (1)
      - neutron-server (11)
      - nova-api-metadata (5)
      - nova-compute (1)
      - qemu-system-x86_64 (2)
      - vault (1)
  debug-logging-enabled:
    neutron: true
    nova: true
  dpkg:
    - conntrack 1:1.4.5-2
    - dnsmasq-base 2.80-1.1ubuntu1.4
    - dnsmasq-utils 2.80-1.1ubuntu1.4
    - haproxy 2.0.13-2ubuntu0.1
    - keepalived 1:2.0.19-2
    - keystone-common 2:17.0.0-0ubuntu0.20.04.1
    - libvirt-daemon 6.0.0-0ubuntu8.11
    - libvirt-daemon-driver-qemu 6.0.0-0ubuntu8.11
    - libvirt-daemon-driver-storage-rbd 6.0.0-0ubuntu8.11
    - libvirt-daemon-system 6.0.0-0ubuntu8.11
    - libvirt-daemon-system-systemd 6.0.0-0ubuntu8.11
    - mysql-common 5.8+1.0.5ubuntu2
    - neutron-common 2:16.4.0-0ubuntu2
    - neutron-dhcp-agent 2:16.4.0-0ubuntu2
    - neutron-fwaas-common 1:16.0.0-0ubuntu0.20.04.1
    - neutron-l3-agent 2:16.4.0-0ubuntu2
    - neutron-metadata-agent 2:16.4.0-0ubuntu2
    - neutron-openvswitch-agent 2:16.4.0-0ubuntu2
    - nova-api-metadata 2:21.2.1-0ubuntu1
    - nova-common 2:21.2.1-0ubuntu1
    - nova-compute 2:21.2.1-0ubuntu1
    - nova-compute-kvm 2:21.2.1-0ubuntu1
    - nova-compute-libvirt 2:21.2.1-0ubuntu1
    - python3-barbicanclient 4.10.0-0ubuntu1
    - python3-cinderclient 1:7.0.0-0ubuntu1
    - python3-designateclient 2.11.0-0ubuntu2
    - python3-glanceclient 1:3.1.1-0ubuntu1
    - python3-keystone 2:17.0.0-0ubuntu0.20.04.1
    - python3-keystoneauth1 4.0.0-0ubuntu1
    - python3-keystoneclient 1:4.0.0-0ubuntu1
    - python3-keystonemiddleware 9.0.0-0ubuntu1
    - python3-neutron 2:16.4.0-0ubuntu2
    - python3-neutron-fwaas 1:16.0.0-0ubuntu0.20.04.1
    - python3-neutron-lib 2.3.0-0ubuntu1
    - python3-neutronclient 1:7.1.1-0ubuntu1
    - python3-nova 2:21.2.1-0ubuntu1
    - python3-novaclient 2:17.0.0-0ubuntu1
    - python3-oslo.cache 2.3.0-0ubuntu1
    - python3-oslo.concurrency 4.0.2-0ubuntu1
    - python3-oslo.config 1:8.0.2-0ubuntu1
    - python3-oslo.context 1:3.0.2-0ubuntu1
    - python3-oslo.db 8.1.0-0ubuntu1
    - python3-oslo.i18n 4.0.1-0ubuntu1
    - python3-oslo.log 4.1.1-0ubuntu1
    - python3-oslo.messaging 12.1.0-0ubuntu1
    - python3-oslo.middleware 4.0.2-0ubuntu1
    - python3-oslo.policy 3.1.0-0ubuntu1.1
    - python3-oslo.privsep 2.1.1-0ubuntu1
    - python3-oslo.reports 2.0.1-0ubuntu1
    - python3-oslo.rootwrap 6.0.2-0ubuntu1
    - python3-oslo.serialization 3.1.1-0ubuntu1
    - python3-oslo.service 2.1.1-0ubuntu1.1
    - python3-oslo.upgradecheck 1.0.1-0ubuntu1
    - python3-oslo.utils 4.1.1-0ubuntu1
    - python3-oslo.versionedobjects 2.0.1-0ubuntu1
    - python3-oslo.vmware 3.3.1-0ubuntu1
    - qemu-kvm 1:4.2-3ubuntu6.17
    - radvd 1:2.17-2
  docker-images:
    - libvirt-exporter 1.1.0
  neutron-l3ha:
    master:
      - 1e086be2-93c2-4740-921d-3e3237f23959
  os-server-external-events:
    network-changed:
      succeeded:
        - port: 03c4d61b-60b0-4f1e-b29c-2554e0c78afd
          instance: 29bcaff8-3d85-43cb-b76f-01bad0e1d568
        - port: 0906171f-17bb-478f-b8fa-9904983b26af
          instance: c050e183-c808-43f9-bdb4-02e95fad58e2
    network-vif-plugged:
      succeeded:
        - port: 03c4d61b-60b0-4f1e-b29c-2554e0c78afd
          instance: 29bcaff8-3d85-43cb-b76f-01bad0e1d568
        - port: 0906171f-17bb-478f-b8fa-9904983b26af
          instance: c050e183-c808-43f9-bdb4-02e95fad58e2
  vm-info:
    running:
      - 29bcaff8-3d85-43cb-b76f-01bad0e1d568
      - c050e183-c808-43f9-bdb4-02e95fad58e2
    vcpu-info:
      used: 2
      system-cores: 2
      available-cores: 2
      overcommit-factor: 1.0
  network:
    namespaces:
      fip: 1
      qrouter: 1
      snat: 1
      qdhcp: 1
    port-health:
      phy-ports:
        br-ens3:
          rx:
            dropped: 131579 (36%)
    config:
      neutron:
        local_ip:
          br-ens3:
            addresses: &id001
              - 10.0.0.49
            hwaddr: 52:54:00:e2:28:a3
            state: UP
      nova:
        my_ip:
          br-ens3:
            addresses: *id001
            hwaddr: 52:54:00:e2:28:a3
            state: UP
      octavia:
        o-hm0:
          o-hm0:
            addresses:
              - fc00:2203:1448:17b7:f816:3eff:fe4f:ed8a
            hwaddr: fa:16:3e:4f:ed:8a
            state: UNKNOWN
  features:
    neutron:
      main:
        availability_zone: nova
      openvswitch-agent:
        l2_population: true
        firewall_driver: openvswitch
      l3-agent:
        agent_mode: dvr_snat
      dhcp-agent:
        enable_metadata_network: true
        enable_isolated_metadata: true
        ovs_use_veth: false
  cpu-pinning-checks:
    input:
      systemd:
        cpuaffinity: 0-7,32-39
  agent-exceptions:
    barbican:
      barbican-api:
        UnicodeDecodeError:
          '2021-10-04': 1
    neutron:
      neutron-openvswitch-agent:
        RuntimeError:
          '2021-10-29': 3
  agent-checks:
    apache:
      connection-refused:
        '2021-10-26':
          127.0.0.1:8981: 3
    neutron-l3ha:
      keepalived:
        transitions:
          1e086be2-93c2-4740-921d-3e3237f23959:
            '2021-10-03': 2
    neutron-ovs-agent:
      rpc-loop:
        top:
          '1329':
            start: 2021-10-03 10:29:51.272000
            end: 2021-10-03 10:29:56.861000
            duration: 5.59
          '1328':
            start: 2021-10-03 10:29:48.591000
            end: 2021-10-03 10:29:51.271000
            duration: 2.68
          '55':
            start: 2021-10-03 09:47:20.938000
            end: 2021-10-03 09:47:22.166000
            duration: 1.23
          '41':
            start: 2021-10-03 09:46:52.597000
            end: 2021-10-03 09:46:54.923000
            duration: 2.33
          '40':
            start: 2021-10-03 09:46:50.151000
            end: 2021-10-03 09:46:52.596000
            duration: 2.44
        stats:
          min: 0.0
          max: 5.59
          stdev: 0.2
          avg: 0.02
          samples: 1389
          incomplete: 2
    neutron-l3-agent:
      router-updates:
        top:
          0339c98d-13d9-4fb1-ab57-3874a3e56c3e:
            start: 2021-10-03 09:46:44.593000
            end: 2021-10-03 09:47:00.692000
            duration: 16.1
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          93350e2d-c717-44fd-a10f-cb6019cce18b:
            start: 2021-10-02 21:53:58.516000
            end: 2021-10-02 21:54:10.683000
            duration: 12.17
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          caa3629f-e401-43d3-a2bf-aa3e6a3bfb6a:
            start: 2021-10-02 21:51:00.306000
            end: 2021-10-02 21:51:16.760000
            duration: 16.45
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          2e401a45-c471-4472-8425-86bdc6ff27b3:
            start: 2021-10-02 21:50:36.610000
            end: 2021-10-02 21:51:00.305000
            duration: 23.7
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          d30df808-c11e-401f-824d-b6f313658455:
            start: 2021-10-02 21:47:53.325000
            end: 2021-10-02 21:48:18.406000
            duration: 25.08
            router: 1e086be2-93c2-4740-921d-3e3237f23959
        stats:
          min: 6.97
          max: 25.08
          stdev: 5.88
          avg: 15.43
          samples: 8
      router-spawn-events:
        top:
          1e086be2-93c2-4740-921d-3e3237f23959:
            start: 2021-10-03 09:46:48.066000
            end: 2021-10-03 09:47:07.617000
            duration: 19.55
        stats:
          min: 19.55
          max: 19.55
          stdev: 0.0
          avg: 19.55
          samples: 1
    nova:
      PciDeviceNotFoundById:
        '2021-10-17':
          0000:3b:10.0: 1
          0000:3b:0f.7: 1
    octavia:
      amp-missed-heartbeats:
        '2021-10-01':
          3604bf2a-ee51-4135-97e2-ec08ed9321db: 1
      lb-failovers:
        auto:
          '2021-10-09':
            7a3b90ed-020e-48f0-ad6f-b28443fa2277: 1
            9cd90142-5501-4362-93ef-1ad219baf45a: 1
            e9cb98af-9c21-4cf6-9661-709179ce5733: 1
            98aefcff-60e5-4087-8ca6-5087ae970440: 1
openvswitch:
  dpkg:
    - libc-bin 2.31-0ubuntu9.2
    - openvswitch-switch 2.13.3-0ubuntu0.20.04.1
  services:
    systemd:
      enabled:
        - openvswitch-switch
      static:
        - ovs-vswitchd
        - ovsdb-server
    ps:
      - ovs-vswitchd (1)
      - ovsdb-client (1)
      - ovsdb-server (1)
  bridges:
    br-data:
      - ens7:
          addresses: []
          hwaddr: 52:54:00:78:19:c3
          state: UP
    br-ex: []
    br-int:
      - (7 ports)
    br-tun:
      - vxlan-0a000032
      - vxlan-0a000030
  daemon-checks:
    ovs-vswitchd:
      netdev-linux-no-such-device:
        '2021-10-19':
          tap4b02cb1d-8b: 1
      bridge-no-such-device:
        '2021-10-29':
          tapd4b5494a-b1: 1
kubernetes:
  snaps:
    - conjure-up 2.6.14-20200716.2107
    - core 16-2.48.2
    - core18 20201210
    - docker 19.03.11
    - go 1.15.6
    - helm 3.5.0
    - kubectl 1.20.2
    - vault 1.5.4
storage:
  ceph:
    release: octopus
    services:
      systemd:
        enabled:
          - ceph-crash
          - ceph-osd
        disabled:
          - ceph-mon
          - ceph-mds
          - ceph-mgr
          - ceph-radosgw
        generated:
          - radosgw
        indirect:
          - ceph-volume
      ps:
        - ceph-crash (1)
        - ceph-osd (1)
    network:
      cluster:
        br-ens3:
          addresses:
            - 10.0.0.49
          hwaddr: 52:54:00:e2:28:a3
          state: UP
      public:
        br-ens3:
          addresses:
            - 10.0.0.49
          hwaddr: 52:54:00:e2:28:a3
          state: UP
    dpkg:
      - ceph 15.2.13-0ubuntu0.20.04.1
      - ceph-base 15.2.13-0ubuntu0.20.04.1
      - ceph-common 15.2.13-0ubuntu0.20.04.1
      - ceph-mds 15.2.13-0ubuntu0.20.04.1
      - ceph-mgr 15.2.13-0ubuntu0.20.04.1
      - ceph-mgr-modules-core 15.2.13-0ubuntu0.20.04.1
      - ceph-mon 15.2.13-0ubuntu0.20.04.1
      - ceph-osd 15.2.13-0ubuntu0.20.04.1
      - python3-ceph-argparse 15.2.13-0ubuntu0.20.04.1
      - python3-ceph-common 15.2.13-0ubuntu0.20.04.1
      - python3-cephfs 15.2.13-0ubuntu0.20.04.1
      - python3-rados 15.2.13-0ubuntu0.20.04.1
      - python3-rbd 15.2.13-0ubuntu0.20.04.1
      - radosgw 15.2.13-0ubuntu0.20.04.1
    local-osds:
      0:
        fsid: 51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea
        dev: /dev/mapper/crypt-51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea
        devtype: ssd
        rss: 639M
    osd-pgs-near-limit:
      osd.1: 501
    osd-pgs-suboptimal:
      osd.1: 501
      osd.0: 295
    versions:
      mon:
        - 15.2.13
      mgr:
        - 15.2.13
      osd:
        - 15.2.13
    osd-reported-failed:
      osd.41:
        '2021-10-13': 23
      osd.85:
        '2021-10-13': 4
    crc-err-bluestore:
      '2021-10-01': 2
    long-heartbeat-pings:
      '2021-10-09': 42
juju:
  version: 2.9.8
  machine: '1'
  charms:
    - ceph-osd-495
    - neutron-openvswitch-443
    - nova-compute-564
  units:
    local:
      - ceph-osd-1
      - neutron-openvswitch-1
      - nova-compute-0
kernel:
  version: 5.4.0-80-generic
  boot: ro
  systemd:
    CPUAffinity: 0-7,32-39
  memory-checks:
    node1-normal:
      - zones:
          10: 0
          9: 0
          8: 0
          7: 0
          6: 0
          5: 0
          4: 0
          3: 1
          2: 54089
          1: 217700
          0: 220376
      - limited high order memory - check ./mysosreport/proc/buddyinfo
    slab-top-consumers:
      - buffer_head (44081.2734375k)
      - anon_vma_chain (6580.0k)
      - anon_vma (5617.390625k)
      - radix_tree_node (30156.984375k)
      - vmap_area (1612.0k)

INFO: see --help for more options

```

## Install

You can either run from this repository directly or install Ubuntu snap e.g.

sudo snap install hotsos --classic

See https://snapcraft.io/hotsos for more info on usage.
