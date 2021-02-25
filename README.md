# hotsos

This tool has two uses; create an application-specific summary of the contents of a [sosreport](https://github.com/sosreport/sos) or a live system and optionally perform extended analysis of those components.

By default all plugins are run but only display information if any is found. If you want to run specific plugins you can choose from a selection (--list-plugins). The default output (stdout) format is yaml to allow easy parsing.

NOTE: hotsos is not intended to replace the functionality of [xsos](https://github.com/ryran/xsos) but rather to provide extra application-specific information to get a useful view of applications running on a host.

### Usage

- Get all information (run all plugins):
```> hotsos /path/to/sos/report
hotsos:
  version: development
  repo-info: 2003fb8
system:
  hostname: acmehost1
  os: ubuntu bionic
  num-cpus: 80
  load: 2.56, 2.44, 2.27
  rootfs: /dev/mapper/vg0-lvroot 364219208 107557132 238091020  32% /
  unattended-upgrades: disabled
openstack:
  release: ussuri
  services:
    - ceilometer-polling (1)
    - dnsmasq (18)
    - haproxy (47)
    - neutron-dhcp-agent (1)
    - neutron-l3-agent (1)
    - neutron-metadata-agent (21)
    - neutron-openvswitch-agent (1)
    - nova-api-metadata (21)
    - nova-compute (1)
    - ovs-vswitchd (1)
    - ovsdb-client (1)
    - ovsdb-server (1)
    - qemu-system-x86_64 (2)
  debug-logging-enabled:
    ceilometer: false
    neutron: false
    nova: false
  instances:
    - 9fcc851a-821e-4a90-8272-fad52e0c5617
    - 5ad5d022-a5ab-472d-8307-894a15e64354
  dpkg:
    - ceilometer-agent-compute 1:14.0.0-0ubuntu0.20.04.1~cloud0
    - ceilometer-common 1:14.0.0-0ubuntu0.20.04.1~cloud0
    - conntrack 1:1.4.4+snapshot20161117-6ubuntu2
    - dnsmasq-base 2.79-1ubuntu0.2
    - dnsmasq-utils 2.79-1ubuntu0.2
    - haproxy 1.8.8-1ubuntu0.11
    - keepalived 1:1.3.9-1ubuntu0.18.04.2
    - keystone-common 2:17.0.0-0ubuntu0.20.04.1~cloud0
    - libc-bin 2.27-3ubuntu1.4
    - libvirt-daemon 6.0.0-0ubuntu8.5~cloud0
    - libvirt-daemon-driver-qemu 6.0.0-0ubuntu8.5~cloud0
    - libvirt-daemon-driver-storage-rbd 6.0.0-0ubuntu8.5~cloud0
    - libvirt-daemon-system 6.0.0-0ubuntu8.5~cloud0
    - libvirt-daemon-system-systemd 6.0.0-0ubuntu8.5~cloud0
    - neutron-common 2:16.2.0-0ubuntu2~cloud0
    - neutron-dhcp-agent 2:16.2.0-0ubuntu2~cloud0
    - neutron-fwaas-common 1:16.0.0-0ubuntu0.20.04.1~cloud0
    - neutron-l3-agent 2:16.2.0-0ubuntu2~cloud0
    - neutron-metadata-agent 2:16.2.0-0ubuntu2~cloud0
    - neutron-openvswitch-agent 2:16.2.0-0ubuntu2~cloud0
    - nova-api-metadata 2:21.1.0-0ubuntu1~cloud0
    - nova-common 2:21.1.0-0ubuntu1~cloud0
    - nova-compute 2:21.1.0-0ubuntu1~cloud0
    - nova-compute-kvm 2:21.1.0-0ubuntu1~cloud0
    - nova-compute-libvirt 2:21.1.0-0ubuntu1~cloud0
    - openvswitch-switch 2.13.1-0ubuntu0.20.04.2~cloud0
    - python3-oslo.cache 2.3.0-0ubuntu1~cloud0
    - python3-oslo.concurrency 4.0.2-0ubuntu1~cloud0
    - python3-oslo.config 1:8.0.2-0ubuntu1~cloud0
    - python3-oslo.context 1:3.0.2-0ubuntu1~cloud0
    - python3-oslo.db 8.1.0-0ubuntu1~cloud0
    - python3-oslo.i18n 4.0.1-0ubuntu1~cloud0
    - python3-oslo.log 4.1.1-0ubuntu1~cloud0
    - python3-oslo.messaging 12.1.0-0ubuntu1~cloud0
    - python3-oslo.middleware 4.0.2-0ubuntu1~cloud0
    - python3-oslo.policy 3.1.0-0ubuntu1.1~cloud0
    - python3-oslo.privsep 2.1.1-0ubuntu1~cloud0
    - python3-oslo.reports 2.0.1-0ubuntu1~cloud0
    - python3-oslo.rootwrap 6.0.2-0ubuntu1~cloud0
    - python3-oslo.serialization 3.1.1-0ubuntu1~cloud0
    - python3-oslo.service 2.1.1-0ubuntu1.1~cloud0
    - python3-oslo.upgradecheck 1.0.1-0ubuntu1~cloud0
    - python3-oslo.utils 4.1.1-0ubuntu1~cloud0
    - python3-oslo.versionedobjects 2.0.1-0ubuntu1~cloud0
    - python3-oslo.vmware 3.3.1-0ubuntu1~cloud0
    - qemu-kvm 1:4.2-3ubuntu6.10~cloud0
  network:
    namespaces:
      qrouter: 1
      qdhcp: 1
      fip: 1
    config:
      nova:
        my_ip: 10.100.22.1 (bond1)
      neutron:
        local_ip: 10.120.22.1 (bond2.231@bond2)
    port-health:
      num-vms-checked: 68
      stats:
        9fcc851a-821e-4a90-8272-fad52e0c5617:
          fa:16:3e:4c:84:c3:
            dropped: 23534 (11%)
        5ad5d022-a5ab-472d-8307-894a15e64354:
          fa:16:3e:97:ce:99:
            dropped: 22236 (10%)
  features:
    neutron:
      neutron:
        availability_zone: az1
      openvswitch-agent:
        l2_population: true
      l3-agent:
        agent_mode: dvr
      dhcp-agent:
        enable_metadata_network: true
        enable_isolated_metadata: true
        ovs_use_veth: false
kubernetes:
  snaps:
    core: 16-2.48.2.1
juju:
  machines:
    running:
      - 40 (version=2.7.6)
  charm-versions:
    - ceilometer-agent-267
    - neutron-openvswitch-278
    - nova-compute-323
    - ntp-39
  units:
    local:
      - ceilometer-agent-14
      - logrotate-41
      - neutron-openvswitch-14
      - nova-compute-4
      - ntp-60
kernel:
  boot: BOOT_IMAGE=/vmlinuz-4.15.0-128-generic root=/dev/mapper/vg0-lvroot ro console=tty0 console=ttyS0,115200 console=ttyS1,115200 raid=noautodetect pti=off
  memory-checks: no issues found
  systemd:
    - CPUAffinity not set

INFO: see --help for more display options
```

## Install

You can either run from this repository directly or install Ubuntu snap e.g.

sudo snap install hotsos

See https://snapcraft.io/hotsos for more info on usage.
