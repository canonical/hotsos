Scenario catalog
================

hotsos ships with a catalog of ready-made *scenario* checks. Each scenario is a
YAML-defined check under ``hotsos/defs/scenarios/`` that inspects the state of a
plugin's application or subsystem and, when its conditions are met, raises an
issue with an actionable message.

This page lists every scenario that hotsos ships, grouped by plugin (and by
subfolder within a plugin), so you can see at a glance what analysis is
available. It is a reference companion to :doc:`plugins` and to
:doc:`../explanation/architecture`, which explains how scenarios are implemented
and run.

The ``Reference`` column links to the upstream bug or CVE a scenario is based on,
where one exists.

Juju plugin
-----------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - charm_unit_checks.yaml
     - Charm units showing leadership errors or tracebacks in their logs.
     - JujuWarning
     - —
   * - juju_binary_cve.yaml
     - Installed Juju binary version affected by known security vulnerabilities.
     - MitreCVE
     - `CVE-2024-3250 <https://www.cve.org/CVERecord?id=CVE-2024-3250>`_,
       `CVE-2024-7558 <https://www.cve.org/CVERecord?id=CVE-2024-7558>`_,
       `CVE-2024-8037 <https://www.cve.org/CVERecord?id=CVE-2024-8037>`_,
       `CVE-2024-8038 <https://www.cve.org/CVERecord?id=CVE-2024-8038>`_
   * - juju_pebble_cve.yaml
     - Pebble snap at vulnerable revision 646.
     - MitreCVE
     - `CVE-2024-3250 <https://www.cve.org/CVERecord?id=CVE-2024-3250>`_
   * - jujud_machine_checks.yaml
     - No jujud process running despite Juju being installed.
     - JujuWarning
     - —
   * - snap_channel.yaml
     - Juju snap installed from a rolling channel instead of a fixed track.
     - JujuWarning
     - —
   * - bugs/lp1812361.yaml
     - Keystone charm is missing required relation data (internal host/port).
     - LaunchpadBug
     - `LP#1812361 <https://bugs.launchpad.net/bugs/1812361>`_
   * - bugs/lp1852502.yaml
     - MongoDB CappedPositionLost scan error affecting Juju controller backups.
     - LaunchpadBug
     - `LP#1852502 <https://bugs.launchpad.net/bugs/1852502>`_
   * - bugs/lp1858519.yaml
     - ceph-osd charm failed to zap a disk due to a residual LVM header.
     - LaunchpadBug
     - `LP#1858519 <https://bugs.launchpad.net/bugs/1858519>`_
   * - bugs/lp1895040.yaml
     - Unknown-relation errors in Juju charm logs.
     - LaunchpadBug
     - `LP#1895040 <https://bugs.launchpad.net/bugs/1895040>`_
   * - bugs/lp1910958.yaml
     - Orphaned relation members preventing charm units from starting.
     - LaunchpadBug
     - `LP#1910958 <https://bugs.launchpad.net/bugs/1910958>`_
   * - bugs/lp1948906.yaml
     - Charm units that failed to complete post-series-upgrade.
     - LaunchpadBug
     - `LP#1948906 <https://bugs.launchpad.net/bugs/1948906>`_
   * - bugs/lp1983140.yaml
     - Juju model migration timed out waiting for agents.
     - LaunchpadBug
     - `LP#1983140 <https://bugs.launchpad.net/bugs/1983140>`_
   * - bugs/lp1983506.yaml
     - Juju model migration hit a local charm binaries error.
     - LaunchpadBug
     - `LP#1983506 <https://bugs.launchpad.net/bugs/1983506>`_
   * - bugs/lp1996230.yaml
     - Action notification collection inconsistencies breaking action retrieval.
     - LaunchpadBug
     - `LP#1996230 <https://bugs.launchpad.net/bugs/1996230>`_

Kernel plugin
-------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - amd_iommu_pt.yaml
     - AMD CPU not using IOMMU passthrough mode for optimal performance.
     - SystemWarning
     - —
   * - disk_failure.yaml
     - Disk hardware errors or block I/O errors in the kernel log.
     - KernelError, KernelWarning
     - —
   * - kernlog_calltrace.yaml
     - Kernel call traces, OOM-killer invocations or hung tasks.
     - KernelError, MemoryWarning
     - —
   * - memory.yaml
     - Memory fragmentation with failed compaction or excessive hugepage use.
     - MemoryWarning
     - —
   * - qla2xxx.yaml
     - QLA2xxx driver skipped a SCSI scan for a non-initiator port.
     - KernelWarning
     - —
   * - scsi_error.yaml
     - SCSI hardware/medium errors or offline devices.
     - KernelError, KernelWarning
     - —

Network
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - misc.yaml
     - Netfilter conntrack table full or over-MTU dropped packets.
     - NetworkWarning
     - —
   * - netlink.yaml
     - Netlink sockets reporting packet drops.
     - NetworkWarning
     - —
   * - tcp.yaml
     - TCP errors including retransmissions, checksum errors and drops.
     - KernelWarning
     - —
   * - udp.yaml
     - UDP errors, buffer exhaustion or memory page usage issues.
     - KernelWarning
     - —

Kubernetes plugin
-----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - ensure_healthy_systemd.yaml
     - Kubernetes systemd units in an invalid or bad state.
     - KubernetesError
     - —
   * - system_cpufreq_mode.yaml
     - Nodes not using the cpufreq scaling governor in performance mode.
     - KubernetesWarning
     - —

Landscape plugin
----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp2081056.yaml
     - landscape-server lock-file contention causing a sync race condition.
     - LaunchpadBug
     - `LP#2081056 <https://bugs.launchpad.net/bugs/2081056>`_

Lxd plugin
----------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - lxcfs_deadlock.yaml
     - LXD 5.9 with lxc containers or libfuse thread exhaustion (lxcfs deadlock).
     - LXDWarning
     - —
   * - snap_channel.yaml
     - LXD snap installed from a rolling channel causing uncontrolled upgrades.
     - LXDWarning
     - —
   * - bugs/lp1807628.yaml
     - LXCFS segfault bug on Bionic requiring a package upgrade.
     - SystemWarning, LaunchpadBug
     - `LP#1807628 <https://bugs.launchpad.net/bugs/1807628>`_

Maas plugin
-----------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - maas_proxy_issue.yaml
     - MAAS proxy unable to forward requests, returning 503 errors.
     - MAASWarning
     - —
   * - maas_regiond_db_connection.yaml
     - MAAS regiond unable to reach its database backend.
     - MAASError
     - —

Microcloud plugin
-----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - snap_channel.yaml
     - microcloud snap installed from a rolling channel causing uncontrolled upgrades.
     - MicroCloudWarning
     - —

Mysql plugin
------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - mysql_connections.yaml
     - MySQL max_connections above 4190 without a charm systemd nofile override.
     - MySQLWarning
     - —
   * - bugs/lp1807628.yaml
     - MySQL max_connections above 4190 without a charm systemd nofile override.
     - MySQLWarning
     - —
   * - bugs/lp1959861.yaml
     - MySQL Router with client SSL mode set but missing client SSL certificate.
     - LaunchpadBug
     - `LP#1959861 <https://bugs.launchpad.net/bugs/1959861>`_
   * - bugs/lp1971565.yaml
     - MySQL Router version affected by a known startup-preventing bug.
     - LaunchpadBug
     - `LP#1971565 <https://bugs.launchpad.net/bugs/1971565>`_
   * - bugs/lp2039444.yaml
     - Cluster add-instance failure when the Juju leader is the highest-numbered unit.
     - LaunchpadBug
     - `LP#2039444 <https://bugs.launchpad.net/bugs/2039444>`_

Openstack plugin
----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - ensure_healthy_systemd.yaml
     - OpenStack systemd units in a bad state (invalid unit files or pending restarts).
     - OpenStackError
     - —
   * - eol.yaml
     - OpenStack release running on the node is end-of-life.
     - OpenstackWarning
     - —
   * - openstack_apache2_certificates.yaml
     - Apache certificates expiring within the configured threshold.
     - OpenstackWarning
     - —
   * - openstack_charm_conflicts.yaml
     - Incompatible charm applications co-located on the same host.
     - OpenstackWarning
     - —
   * - pkgs_from_mixed_releases_found.yaml
     - OpenStack packages from multiple releases installed on the same host.
     - OpenstackWarning
     - —
   * - system_cpufreq_mode.yaml
     - CPU frequency governor set to performance mode on OpenStack nodes.
     - OpenstackWarning
     - —
   * - systemd_masked_services.yaml
     - OpenStack systemd services that are unexpectedly masked.
     - OpenstackWarning
     - —
   * - token_auth_failed.yaml
     - Token authorization failures in OpenStack API services.
     - OpenstackWarning
     - —

Barbican
~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp1946787.yaml
     - Barbican versions with a bug preventing Cinder encrypted-volume creation.
     - LaunchpadBug
     - `LP#1946787 <https://bugs.launchpad.net/bugs/1946787>`_

Cinder
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp2004555.yaml
     - Cinder packages vulnerable to CVE-2023-2088 and whether service tokens are enabled.
     - UbuntuCVE, OpenstackWarning
     - `CVE-2023-2088 <https://ubuntu.com/security/CVE-2023-2088>`_
   * - bugs/lp2059809.yaml
     - Cinder packages vulnerable to CVE-2024-32498 across releases.
     - UbuntuCVE
     - `CVE-2024-32498 <https://ubuntu.com/security/CVE-2024-32498>`_
   * - bugs/lp2085851.yaml
     - Cinder versions with a known regression in specific releases.
     - LaunchpadBug
     - `LP#2085851 <https://bugs.launchpad.net/bugs/2085851>`_

Glance
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp2059809.yaml
     - Glance packages vulnerable to CVE-2024-32498 when image conversion is enabled.
     - UbuntuCVE
     - `CVE-2024-32498 <https://ubuntu.com/security/CVE-2024-32498>`_

Keystone
~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp1896125.yaml
     - Keystone LDAP connection-pool errors causing denial of service when pooling is on.
     - LaunchpadBug
     - `LP#1896125 <https://bugs.launchpad.net/bugs/1896125>`_

Masakari
~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - pacemaker_remote.yaml
     - Whether pacemaker-remote is installed and enabled on Masakari compute hosts.
     - OpenstackWarning
     - —

Neutron
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - neutron_ovs_cleanup.yaml
     - Whether the neutron-ovs-cleanup systemd service has been manually run.
     - OpenstackWarning
     - —
   * - oslo_privsep_errors.yaml
     - privsep daemon buffer overflows in neutron agents and buggy oslo.privsep versions.
     - OpenStackError, LaunchpadBug
     - `LP#2029952 <https://bugs.launchpad.net/bugs/2029952>`_
   * - ovn_stale_db.yaml
     - Frequent OVN database reconnections indicating stale data.
     - Bugzilla
     - `BZ#1829109 <https://bugzilla.redhat.com/show_bug.cgi?id=1829109>`_
   * - ovndb_leader_bouncing.yaml
     - Frequent OVN NB/SB leader changes degrading neutron-server performance.
     - OpenstackWarning
     - —
   * - bugs/lp1794991.yaml
     - openvswitch-switch restarted after the OVS agent, risking inconsistent l2pop flows.
     - LaunchpadBug
     - `LP#1794991 <https://bugs.launchpad.net/bugs/1794991>`_
   * - bugs/lp1883089.yaml
     - neutron l3-agent AttributeError affecting DVR floating IPs.
     - LaunchpadBug
     - `LP#1883089 <https://bugs.launchpad.net/bugs/1883089>`_
   * - bugs/lp1896506.yaml
     - Unsupported keepalived configuration emitted by the neutron l3-agent.
     - LaunchpadBug
     - `LP#1896506 <https://bugs.launchpad.net/bugs/1896506>`_
   * - bugs/lp1907686.yaml
     - OVN database connection timeouts in the OVS agent on hosts with isolated CPUs.
     - LaunchpadBug
     - `LP#1907686 <https://bugs.launchpad.net/bugs/1907686>`_
   * - bugs/lp1927868.yaml
     - neutron-common versions with a known critical bug for non-OVN deployments.
     - LaunchpadBug
     - `LP#1927868 <https://bugs.launchpad.net/bugs/1927868>`_
   * - bugs/lp1928031.yaml
     - OVN southbound database connection errors in the OVN metadata agent.
     - LaunchpadBug
     - `LP#1928031 <https://bugs.launchpad.net/bugs/1928031>`_
   * - bugs/lp1929832.yaml
     - l3-agent router deletion errors from rootwrap authorization issues.
     - LaunchpadBug
     - `LP#1929832 <https://bugs.launchpad.net/bugs/1929832>`_
   * - bugs/lp1948466.yaml
     - neutron-server errors deleting subnets from OVN via maintenance tasks.
     - LaunchpadBug
     - `LP#1948466 <https://bugs.launchpad.net/bugs/1948466>`_
   * - bugs/lp1960319.yaml
     - Missing openvswitch-common causing neutron-server ovsdb-client errors.
     - LaunchpadBug
     - `LP#1960319 <https://bugs.launchpad.net/bugs/1960319>`_
   * - bugs/lp1965297.yaml
     - l3-agent errors on HA routers that can stall router updates.
     - LaunchpadBug
     - `LP#1965297 <https://bugs.launchpad.net/bugs/1965297>`_
   * - bugs/lp1979089.yaml
     - l3-agent respawning haproxy for a deleted router due to a missing namespace.
     - LaunchpadBug
     - `LP#1979089 <https://bugs.launchpad.net/bugs/1979089>`_
   * - bugs/lp1980211.yaml
     - python3-openvswitch versions with an OVN southbound reconnection bug.
     - LaunchpadBug, OpenstackWarning
     - `LP#1980211 <https://bugs.launchpad.net/bugs/1980211>`_
   * - bugs/lp1993628.yaml
     - DuplicateRecordSet exceptions where external DNS zones fail to update on port delete.
     - LaunchpadBug
     - `LP#1993628 <https://bugs.launchpad.net/bugs/1993628>`_
   * - bugs/lp1996594.yaml
     - OVN metadata agent randomly stopping metadata requests due to OVSDB errors.
     - LaunchpadBug
     - `LP#1996594 <https://bugs.launchpad.net/bugs/1996594>`_
   * - bugs/lp2017748.yaml
     - OVN metadata agent tearing down metadata namespaces prematurely under load.
     - LaunchpadBug
     - `LP#2017748 <https://bugs.launchpad.net/bugs/2017748>`_
   * - bugs/lp2084977.yaml
     - neutron-server failing to delete security groups with OVN port-group errors.
     - LaunchpadBug
     - `LP#2084977 <https://bugs.launchpad.net/bugs/2084977>`_
   * - bugs/lp2094842.yaml
     - neutron-server OVSDB errors when router gateways lack subnets in external networks.
     - LaunchpadBug
     - `LP#2094842 <https://bugs.launchpad.net/bugs/2094842>`_
   * - bugs/lp2148650.yaml
     - neutron-server stuck retrying an OVN IPsec VPN service due to CIDR overlap.
     - LaunchpadBug
     - `LP#2148650 <https://bugs.launchpad.net/bugs/2148650>`_

Nova
~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - config_checks.yaml
     - DPDK configuration correctness for nova-compute, including queue sizes.
     - OpenstackWarning
     - —
   * - cpu_pinning.yaml
     - CPU pinning consistency between kernel, systemd and nova settings.
     - OpenstackWarning, OpenStackError
     - —
   * - service_mem_usage.yaml
     - libvirtd memory usage above 5G indicating a possible memory leak.
     - OpenstackWarning, LaunchpadBug
     - `LP#2024114 <https://bugs.launchpad.net/bugs/2024114>`_
   * - bugs/lp1761062.yaml
     - VM resize failures on RBD backends from leftover instance folders.
     - LaunchpadBug
     - `LP#1761062 <https://bugs.launchpad.net/bugs/1761062>`_
   * - bugs/lp1860743.yaml
     - Live migration failures with SSH host-key verification errors in nova-compute.
     - LaunchpadBug
     - `LP#1860743 <https://bugs.launchpad.net/bugs/1860743>`_
   * - bugs/lp1888395.yaml
     - Live migration failures without multiple-port-binding support on neutron.
     - LaunchpadBug
     - `LP#1888395 <https://bugs.launchpad.net/bugs/1888395>`_
   * - bugs/lp1904580.yaml
     - nova-compute upgrade issues with overly permissive private SSH key permissions.
     - LaunchpadBug
     - `LP#1904580 <https://bugs.launchpad.net/bugs/1904580>`_
   * - bugs/lp1944619.yaml
     - nova-compute failures attaching network adapters with libvirt PCI errors.
     - LaunchpadBug
     - `LP#1944619 <https://bugs.launchpad.net/bugs/1944619>`_
   * - bugs/lp1967956.yaml
     - VM image resize failures on CIS-hardened nodes with permission errors.
     - LaunchpadBug
     - `LP#1967956 <https://bugs.launchpad.net/bugs/1967956>`_
   * - bugs/lp1972028.yaml
     - nova race condition polling libvirt for PCI passthrough devices.
     - LaunchpadBug
     - `LP#1972028 <https://bugs.launchpad.net/bugs/1972028>`_
   * - bugs/lp2004555.yaml
     - Nova packages vulnerable to CVE-2023-2088 and whether service tokens are enabled.
     - UbuntuCVE, OpenstackWarning
     - `CVE-2023-2088 <https://ubuntu.com/security/CVE-2023-2088>`_
   * - bugs/lp2012284.yaml
     - nova-compute failures when osinfo is installed and apparmor is enforcing.
     - LaunchpadBug
     - `LP#2012284 <https://bugs.launchpad.net/bugs/2012284>`_
   * - bugs/lp2059809.yaml
     - Nova packages vulnerable to CVE-2024-32498 across releases.
     - UbuntuCVE
     - `CVE-2024-32498 <https://ubuntu.com/security/CVE-2024-32498>`_
   * - bugs/lp2091033.yaml
     - nova-compute with vGPU enabled on versions with a known critical bug.
     - LaunchpadBug
     - `LP#2091033 <https://bugs.launchpad.net/bugs/2091033>`_

Octavia
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - excessive_failovers.yaml
     - Excessive automatic load-balancer failovers indicating network/config issues.
     - OpenstackWarning
     - —
   * - hm_port_health.yaml
     - Octavia health-manager port address configuration and packet drops.
     - OpenstackError
     - —
   * - bugs/lp2029857.yaml
     - Octavia API errors when the OVN provider driver is enabled.
     - LaunchpadBug
     - `LP#2029857 <https://bugs.launchpad.net/bugs/2029857>`_
   * - bugs/sb1896125.yaml
     - Octavia load-balancer failover failures when pool session persistence is set.
     - StoryBoardBug
     - `SB#2008099 <https://storyboard.openstack.org/#!/story/2008099>`_

OpenStack charms
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - nova_cc_ssh_known_hosts_fail.yaml
     - nova-cloud-controller failing to populate SSH known_hosts for nova-compute units.
     - OpenstackWarning
     - —

Oslo messaging
~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - lp1934937.yaml
     - greenlet errors in services using oslo.messaging with a threaded heartbeat.
     - LaunchpadBug
     - `LP#1934937 <https://bugs.launchpad.net/bugs/1934937>`_

Sunbeam
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - pods.yaml
     - Sunbeam controller pods not in Running status.
     - OpenStackError
     - —
   * - stable_release.yaml
     - Whether the Sunbeam OpenStack snap is on a supported stable channel.
     - OpenStackError
     - —
   * - statefulsets.yaml
     - Sunbeam OpenStack statefulsets that are incomplete.
     - OpenStackError
     - —

Openvswitch plugin
------------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - dpdk_config.yaml
     - OVS DPDK configuration missing or with overlapping CPU masks.
     - OpenvSwitchWarning
     - —
   * - dpif_lost_packets.yaml
     - OVS datapath reporting lost packets indicating kernel drops.
     - OpenvSwitchWarning
     - —
   * - fdb_wrapping.yaml
     - FDB table full and wrapping, hurting OVS performance.
     - OpenvSwitchWarning
     - —
   * - service_restarts.yaml
     - ovs-vswitchd service restarting very frequently.
     - OpenvSwitchWarning
     - —
   * - bugs/lp1839592.yaml
     - libc version with a critical bug causing OVS deadlocks.
     - LaunchpadBug
     - `LP#1839592 <https://bugs.launchpad.net/bugs/1839592>`_
   * - bugs/lp1978806.yaml
     - Conntrack tracking encapsulated tunnel traffic unnecessarily.
     - LaunchpadBug
     - `LP#1978806 <https://bugs.launchpad.net/bugs/1978806>`_

OVN
~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bfd_flapping.yaml
     - Frequent BFD state changes or gateway port reassignments.
     - OVNWarning
     - —
   * - ovn_central_certs_logs.yaml
     - OVN central services with invalid or expired SSL certificates.
     - OVNWarning
     - —
   * - ovn_central_services.yaml
     - OVN northd service not running on the central node.
     - OVNError
     - —
   * - ovn_certs_valid.yaml
     - OVN central or Neutron ML2 SSL certificates missing or expiring soon.
     - OVNError
     - —
   * - ovn_chassis_certs_logs.yaml
     - ovn-controller with invalid or expired SSL certificates.
     - OVNWarning
     - —
   * - ovn_elections.yaml
     - OVN database experiencing frequent raft elections.
     - OVNWarning
     - —
   * - ovn_upgrades.yaml
     - OVN northd version mismatch causing service issues.
     - OVNError, LaunchpadBug
     - `LP#2030944 <https://bugs.launchpad.net/bugs/2030944>`_
   * - bugs/lp1865127.yaml
     - "No bridge for localnet port" error spam in ovn-controller logs.
     - LaunchpadBug
     - `LP#1865127 <https://bugs.launchpad.net/bugs/1865127>`_
   * - bugs/lp1917475.yaml
     - OVN database RBAC permission errors in ovn-controller logs.
     - LaunchpadBug
     - `LP#1917475 <https://bugs.launchpad.net/bugs/1917475>`_
   * - bugs/lp1995078.yaml
     - Active gateway chassis not matching the HA chassis group, losing port connectivity.
     - LaunchpadBug
     - `LP#1995078 <https://bugs.launchpad.net/bugs/1995078>`_
   * - bugs/lp2122319.yaml
     - Incompatible port-change warnings for SmartNIC offloaded ports.
     - LaunchpadBug
     - `LP#2122319 <https://bugs.launchpad.net/bugs/2122319>`_
   * - bugs/lp2127934.yaml
     - ovn-controller retry loop from Learned_Route constraint violations.
     - LaunchpadBug
     - `LP#2127934 <https://bugs.launchpad.net/bugs/2127934>`_
   * - bugs/lp2143751.yaml
     - Manually registered LRP in Gateway_Chassis incompatible with the Neutron scheduler.
     - LaunchpadBug
     - `LP#2143751 <https://bugs.launchpad.net/bugs/2143751>`_

Pacemaker plugin
----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bugs/lp1874719.yaml
     - Pacemaker cluster node named "node1" that must be removed due to a known bug.
     - LaunchpadBug
     - `LP#1874719 <https://bugs.launchpad.net/bugs/1874719>`_

Rabbitmq plugin
---------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - cluster_config.yaml
     - Partition handling set to "ignore" instead of "pause_minority".
     - RabbitMQWarning
     - —
   * - cluster_logchecks.yaml
     - Cluster partitions, mirrored-queue sync issues or message discard events.
     - RabbitMQWarning
     - —
   * - cluster_resources.yaml
     - Nodes holding more than two thirds of the queues for one or more vhosts.
     - RabbitMQWarning
     - —
   * - no_consumer_queues.yaml
     - Queues with unacknowledged messages but no active consumers.
     - RabbitMQWarning
     - —
   * - bugs/lp1943937.yaml
     - RabbitMQ queues stuck with timeout errors during declare operations.
     - LaunchpadBug
     - `LP#1943937 <https://bugs.launchpad.net/bugs/1943937>`_

Sosreport plugin
----------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - plugin_timeouts.yaml
     - sosreport plugins that timed out during collection, giving incomplete data.
     - SOSReportWarning
     - —

Storage plugin
--------------

Bcache
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bcache.yaml
     - Placeholder scenario; no checks are run for LXC containers.
     - —
     - —
   * - bdev.yaml
     - Invalid bcache bdev configuration (sequential cutoff, cache mode, writeback).
     - BcacheWarning
     - —
   * - cacheset.yaml
     - Invalid bcache cacheset thresholds and low cache availability.
     - BcacheWarning, LaunchpadBug
     - `LP#1900438 <https://bugs.launchpad.net/bugs/1900438>`_

Ceph
~~~~

Ceph MGR
^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - autoscaler_overlap_roots.yaml
     - Overlapping CRUSH roots preventing the PG autoscaler from scaling pools.
     - CephMgrError
     - —

Ceph MON
^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - auth_insecure_global_id_reclaim.yaml
     - Clients/daemons using insecure global_id reclaim (CVE-2021-20288).
     - MitreCVE
     - `CVE-2021-20288 <https://www.cve.org/CVERecord?id=CVE-2021-20288>`_
   * - auth_insecure_global_id_reclaim_allowed.yaml
     - Cluster allowing insecure global_id reclaim, blocking HEALTH_OK.
     - CephWarning
     - —
   * - autoscaler_bug.yaml
     - Ceph versions with a PG autoscaler memory-leak bug.
     - CephTrackerBug
     - `Ceph#53729 <https://tracker.ceph.com/issues/53729>`_
   * - bluefs_size.yaml
     - BlueFS metadata consuming excessive device space (compaction failure).
     - CephTrackerBug
     - `Ceph#45903 <https://tracker.ceph.com/issues/45903>`_
   * - bluefs_spillover.yaml
     - RocksDB spillover from BlueFS exceeding leveled space.
     - CephTrackerBug
     - `Ceph#38745 <https://tracker.ceph.com/issues/38745>`_
   * - capacity_ratio_overrides.yaml
     - Ceph capacity ratios overridden above safe defaults.
     - CephMonWarning
     - —
   * - ceph_address_overlap.yaml
     - Overlapping cluster_network and public_network configuration.
     - CephWarning
     - —
   * - ceph_cluster_health.yaml
     - Cluster not in HEALTH_OK state.
     - CephWarning
     - —
   * - ceph_versions_mismatch.yaml
     - Misaligned Ceph daemon versions across the cluster.
     - CephDaemonWarning, CephDaemonVersionsError
     - —
   * - crushmap_bucket_checks.yaml
     - Mixed bucket types and unbalanced buckets in the CRUSH map.
     - CephCrushWarning
     - —
   * - crushmap_osd_count_imbalance.yaml
     - Significant OSD-count imbalance across failure-domain buckets.
     - CephCrushWarning
     - —
   * - empty_clog.yaml
     - Empty ceph cluster log file preventing log monitoring.
     - CephTrackerBug
     - `Ceph#55383 <https://tracker.ceph.com/issues/55383>`_
   * - eol.yaml
     - Ceph release past end of life.
     - CephWarning
     - —
   * - laggy_pgs.yaml
     - Laggy or waiting placement groups in the cluster.
     - CephWarning
     - —
   * - large_omap_objects.yaml
     - Placement groups with large OMAP objects.
     - CephWarning
     - —
   * - manual_upmap_failure_domain.yaml
     - Manual pg-upmap placements violating failure-domain constraints.
     - CephCrushWarning
     - —
   * - mds_balancer.yaml
     - CephFS with the MDS balancer enabled causing stability issues.
     - CephTrackerBug
     - `Ceph#61378 <https://tracker.ceph.com/issues/61378>`_
   * - meta_backend_mon.yaml
     - Monitors using the deprecated leveldb backend instead of rocksdb.
     - CephMonWarning
     - —
   * - mon_db_too_big.yaml
     - Monitor leveldb database consuming excessive disk space.
     - CephMonWarning
     - —
   * - mon_elections_flapping.yaml
     - Frequent monitor re-elections within 24-hour periods.
     - CephWarning
     - —
   * - osd_flapping.yaml
     - OSDs repeatedly restarting due to network or hardware issues.
     - CephOSDError, CephWarning
     - —
   * - osd_maps_backlog_too_large.yaml
     - Excessive OSD map backlog affecting monitor performance.
     - CephMapsWarning
     - —
   * - osd_messenger_v2_protocol.yaml
     - OSD cluster members not using the messenger v2 protocol.
     - CephOSDWarning
     - —
   * - osd_missing_device_class.yaml
     - OSDs without a device class in the CRUSH map.
     - CephOSDWarning
     - —
   * - osd_mixed_size_disks.yaml
     - OSDs of different sizes within the same device class.
     - CephOSDWarning
     - —
   * - osd_slow_heartbeats.yaml
     - Slow heartbeats between OSDs indicating network issues.
     - CephOSDError
     - —
   * - osd_slow_ops.yaml
     - Slow I/O operations between OSDs.
     - CephOSDError, CephWarning
     - —
   * - osd_unusual_raw.yaml
     - OSDs with raw usage exceeding data+meta+omap+bluefs combined.
     - CephOSDWarning
     - —
   * - pg_imbalance.yaml
     - OSDs with PG counts outside optimal ranges.
     - CephCrushError, CephCrushWarning
     - —
   * - pg_overdose.yaml
     - Cluster hitting the hard limit for PGs per OSD.
     - CephWarning
     - —
   * - pool_size_min_size.yaml
     - Pools where size equals min_size, with no failure tolerance.
     - CephWarning
     - —
   * - recent_laggy_pgs.yaml
     - Recent laggy placement groups in the logs.
     - CephWarning
     - —
   * - required_osd_release_mismatch.yaml
     - OSDs not matching the cluster require_osd_release setting.
     - CephOSDError
     - —
   * - rgw_frontend.yaml
     - RGW configured to use the deprecated civetweb frontend.
     - CephRGWWarning
     - —
   * - ssds_using_bcache.yaml
     - SSD OSDs configured with bcache, which typically hurts performance.
     - CephOSDWarning
     - —
   * - unresponsive_mon_mgr.yaml
     - Unresponsive mon/mgr daemons inferred from incomplete command output.
     - CephMonWarning
     - —

Ceph OSD
^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - bluefs_log_size.yaml
     - BlueFS log files grown beyond 50 GiB consuming device space.
     - CephOSDError
     - —
   * - ceph_address_overlap.yaml
     - Overlapping cluster and public network configuration.
     - CephWarning
     - —
   * - delete_workload_bug.yaml
     - Ceph OSD version with a critical delete-workload performance bug.
     - CephOSDWarning
     - —
   * - eol.yaml
     - OSD running an end-of-life Ceph version.
     - CephWarning
     - —
   * - filestore_to_bluestore_upgrade.yaml
     - BlueStore enabled with a journal device still configured.
     - CephWarning
     - —
   * - juju_ceph_no_bcache_tuning.yaml
     - Juju-managed Ceph OSDs using bcache without the bcache-tuning charm.
     - BcacheWarning
     - —
   * - meta_backend_osd.yaml
     - OSDs using the deprecated leveldb backend instead of rocksdb.
     - CephMonWarning
     - —
   * - osd_crashes.yaml
     - OSD daemon crashes with signals and assertions.
     - CephOSDError
     - —
   * - osd_flapping.yaml
     - OSDs repeatedly restarting.
     - CephOSDError, CephWarning
     - —
   * - osd_latency.yaml
     - Slow I/O operations with 5+ second latencies in OSD logs.
     - CephOSDWarning
     - —
   * - osd_slow_ops.yaml
     - Slow OSD operations.
     - CephOSDError, CephWarning
     - —
   * - pg_overdose.yaml
     - OSDs unable to create PGs due to hard limits.
     - CephOSDWarning
     - —
   * - rocksdb_compaction_errors.yaml
     - RocksDB compaction, corruption and I/O errors.
     - CephOSDError
     - —
   * - small_bluestore_db.yaml
     - BlueStore DB devices smaller than 4% of the OSD block device.
     - CephOSDWarning
     - —
   * - system_cpufreq_mode.yaml
     - OSDs running with a CPU governor not set to performance.
     - CephWarning
     - —
   * - bugs/lp1936136.yaml
     - Ceph OSD versions using bcache with low cache availability.
     - LaunchpadBug
     - `LP#1936136 <https://bugs.launchpad.net/bugs/1936136>`_
   * - bugs/lp1959649.yaml
     - Octopus OSD version vulnerable to a RocksDB disk-space bug.
     - LaunchpadBug
     - `LP#1959649 <https://bugs.launchpad.net/bugs/1959649>`_
   * - bugs/lp1996010.yaml
     - BlueStore onode cache potentially disabled due to a mempool leak.
     - LaunchpadBug
     - `LP#1996010 <https://bugs.launchpad.net/bugs/1996010>`_
   * - bugs/lp2013960.yaml
     - Ceph Quincy version without the 17.2.6+ fix.
     - LaunchpadBug
     - `LP#2013960 <https://bugs.launchpad.net/bugs/2013960>`_
   * - bugs/lp2016845.yaml
     - Ceph OSDs not linked with the tcmalloc library.
     - LaunchpadBug
     - `LP#2016845 <https://bugs.launchpad.net/bugs/2016845>`_

Ceph RGW
^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - rgw_frontend_rgw.yaml
     - RGW using the deprecated civetweb frontend instead of beast.
     - CephRGWWarning
     - —
   * - rgw_s3_auth_order.yaml
     - RGW with local auth before external (Keystone) auth in the S3 auth order.
     - CephRGWWarning
     - —
   * - bugs/lp1974138.yaml
     - Missing or disabled AllowEncodedSlashes in the Apache RGW setup.
     - LaunchpadBug
     - `LP#1974138 <https://bugs.launchpad.net/bugs/1974138>`_

Common
^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - ceph_charm_conflicts.yaml
     - Multiple conflicting Ceph charms deployed on the same host.
     - CephWarning
     - —
   * - ensure_healthy_systemd.yaml
     - Ceph systemd units in a bad state.
     - CephError
     - —
   * - bugs/lp2071780.yaml
     - CephFS charm restarting the MDS too frequently on config changes.
     - LaunchpadBug
     - `LP#2071780 <https://bugs.launchpad.net/bugs/2071780>`_

NFS
~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - nfs-detect-mount-name-resolution-failure.yaml
     - NFS mount failures due to hostname resolution errors.
     - NFSNameResolutionError
     - —

SmartCtl
~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - unhealthy_disks.yaml
     - Disks reported as unhealthy by smartctl.
     - SmartCtlWarning
     - —

System plugin
-------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - cve-libmodule-scandeps-perl.yaml
     - libmodule-scandeps-perl installed with vulnerability CVE-2024-10224.
     - MitreCVE
     - `CVE-2024-10224 <https://www.cve.org/CVERecord?id=CVE-2024-10224>`_
   * - cve-needrestart.yaml
     - needrestart installed with vulnerability CVE-2024-48990.
     - MitreCVE
     - `CVE-2024-48990 <https://www.cve.org/CVERecord?id=CVE-2024-48990>`_
   * - cve-rsync.yaml
     - rsync installed with vulnerability CVE-2024-12084.
     - MitreCVE
     - `CVE-2024-12084 <https://www.cve.org/CVERecord?id=CVE-2024-12084>`_
   * - rsyslog-read-syslog.yaml
     - rsyslog configured to read /var/log/syslog, risking a logging loop.
     - SystemWarning
     - —
   * - sssd-ad-tokengroups.yaml
     - SSSD AD domains with ldap_use_tokengroups enabled, breaking group membership.
     - SSSDWarning
     - —
   * - unattended_upgrades.yaml
     - Unattended upgrades enabled, allowing uncontrolled system changes.
     - SystemWarning
     - —

Vault plugin
------------

Common
~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 26 40 18 16

   * - Scenario
     - Checks for
     - Raises
     - Reference
   * - snap_channel.yaml
     - vault snap installed from a rolling channel causing uncontrolled upgrades.
     - VaultWarning
     - —
