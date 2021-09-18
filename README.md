# hotsos

Collect information about specific applications and raise issues when problems are detected. Can be run against host or sosreport.

A number of application plugins are supported including Openstack, Ceph, Kubernetes, Juju and more. The standard output is structured YAML format.

By default all plugins are run and only produce ouput if applicable. If you want to run specific plugins you can choose from a selection (--list-plugins). See --help for more options.

### Usage

- Run hotsos against a sosreport (by default runs all plugins)

```
$ hotsos ./mysosreport
INFO: analysing sosreport at ./mysosreport
hotsos:
  version: 309
  repo-info: 68239cd
system:
  hostname: compute4
  os: ubuntu focal
  num-cpus: 2
  unattended-upgrades: ENABLED
openstack:
  services:
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
    config:
      neutron:
        local_ip: 10.0.0.49 (ens3)
      nova:
        my_ip: 10.0.0.49 (ens3)
  features:
    neutron:
      neutron:
        availability_zone: nova
      openvswitch-agent:
        l2_population: true
      l3-agent:
        agent_mode: dvr_snat
      dhcp-agent:
        enable_metadata_network: true
        enable_isolated_metadata: true
        ovs_use_veth: false
  agent-exceptions:
    neutron:
      neutron-openvswitch-agent:
        MessagingTimeout:
          '2021-08-02': 6
          '2021-08-03': 32
      neutron-l3-agent:
        MessagingTimeout:
          '2021-08-02': 6
          '2021-08-03': 32
  neutron-l3ha:
    agent:
      master:
        - 1e086be2-93c2-4740-921d-3e3237f23959
    keepalived:
      transitions:
        1e086be2-93c2-4740-921d-3e3237f23959:
          '2021-08-03': 2
  agent-checks:
    neutron-ovs-agent:
      rpc-loop:
        top:
          '1329':
            start: 2021-08-03 10:29:51.272000
            end: 2021-08-03 10:29:56.861000
            duration: 5.59
          '1328':
            start: 2021-08-03 10:29:48.591000
            end: 2021-08-03 10:29:51.271000
            duration: 2.68
          '55':
            start: 2021-08-03 09:47:20.938000
            end: 2021-08-03 09:47:22.166000
            duration: 1.23
          '41':
            start: 2021-08-03 09:46:52.597000
            end: 2021-08-03 09:46:54.923000
            duration: 2.33
          '40':
            start: 2021-08-03 09:46:50.151000
            end: 2021-08-03 09:46:52.596000
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
            start: 2021-08-03 09:46:44.593000
            end: 2021-08-03 09:47:00.692000
            duration: 16.1
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          93350e2d-c717-44fd-a10f-cb6019cce18b:
            start: 2021-08-02 21:53:58.516000
            end: 2021-08-02 21:54:10.683000
            duration: 12.17
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          caa3629f-e401-43d3-a2bf-aa3e6a3bfb6a:
            start: 2021-08-02 21:51:00.306000
            end: 2021-08-02 21:51:16.760000
            duration: 16.45
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          2e401a45-c471-4472-8425-86bdc6ff27b3:
            start: 2021-08-02 21:50:36.610000
            end: 2021-08-02 21:51:00.305000
            duration: 23.7
            router: 1e086be2-93c2-4740-921d-3e3237f23959
          d30df808-c11e-401f-824d-b6f313658455:
            start: 2021-08-02 21:47:53.325000
            end: 2021-08-02 21:48:18.406000
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
            start: 2021-08-03 09:46:48.066000
            end: 2021-08-03 09:47:07.617000
            duration: 19.55
        stats:
          min: 19.55
          max: 19.55
          stdev: 0.0
          avg: 19.55
          samples: 1
openvswitch:
  dpkg:
    - libc-bin 2.31-0ubuntu9.2
    - openvswitch-switch 2.13.3-0ubuntu0.20.04.1
  services:
    - ovs-vswitchd (1)
    - ovsdb-client (1)
    - ovsdb-server (1)
  port-stats:
    qr-aa623763-fd:
      RX:
        packets: 309
        dropped: 1394875
storage:
  ceph:
    services:
      - ceph-crash (1)
      - ceph-osd (1)
    dpkg:
      - ceph-base 15.2.13-0ubuntu0.20.04.1
      - ceph-common 15.2.13-0ubuntu0.20.04.1
      - ceph-mds 15.2.13-0ubuntu0.20.04.1
      - ceph-mgr 15.2.13-0ubuntu0.20.04.1
      - ceph-mgr-modules-core 15.2.13-0ubuntu0.20.04.1
      - ceph-mon 15.2.13-0ubuntu0.20.04.1
      - ceph-osd 15.2.13-0ubuntu0.20.04.1
      - python3-ceph-argparse 15.2.13-0ubuntu0.20.04.1
      - python3-ceph-common 15.2.13-0ubuntu0.20.04.1
      - python3-rbd 15.2.13-0ubuntu0.20.04.1
      - radosgw 15.2.13-0ubuntu0.20.04.1
    osds:
      0:
        fsid: 51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea
        dev: /dev/mapper/crypt-51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea
        rss: 639M
    versions:
      mon:
        - 15.2.13
      mgr:
        - 15.2.13
      osd:
        - 15.2.13
      rgw:
        - 15.2.13
  bcache:
    devices:
      bcache:
        bcache0:
          dname: bcache1
        bcache1:
          dname: bcache0
    cachesets:
      - uuid: 2bb274af-a015-4496-9455-43393ea06aa2
        cache_available_percent: 95
juju:
  machines:
    running:
      - 1 (version=2.9.8)
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
  memory-checks: no issues found
  systemd:
    - CPUAffinity not set

INFO: see --help for more options

```

## Install

You can either run from this repository directly or install Ubuntu snap e.g.

sudo snap install hotsos

See https://snapcraft.io/hotsos for more info on usage.
