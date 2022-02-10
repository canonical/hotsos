# Overview

The nova-compute charm deploys [Nova Compute][upstream-compute], the core
OpenStack service that provisions virtual instances (VMs) and baremetal servers
(via [Ironic][cdg-ironic]). The charm works alongside other Juju-deployed
OpenStack services.

# Usage

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. See the [Juju documentation][juju-docs-config-apps] for details
on configuring applications.

#### `config-flags`

A comma-separated list of key=value configuration flags. These values will be
placed in the [DEFAULT] section of the `nova.conf` file.

#### `enable-live-migration`

Allows the live migration of VMs.

#### `enable-resize`

Allows the resizing of VMs.

#### `migration-auth-type`

Selects the TCP authentication scheme to use for live migration. The only
accepted value is 'ssh'.

#### `customize-failure-domain`

When MAAS is the backing cloud and this option is set to 'true' then all
MAAS-defined zones will become available as Nova availability zones, and option
`default-availability-zone` will be overridden. See section [Availability
Zones][anchor-az].

#### `default-availability-zone`

Sets a single default Nova availability zone. It is used when a VM is created
without a Nova AZ being specified. The default value is 'nova'. A non-default
Nova AZ must be created manually (i.e. `openstack aggregate create`). See
section [Availability Zones][anchor-az].

#### `libvirt-image-backend`

Specifies what image backend to use. Possible values are 'rbd', 'qcow2',
'raw', and 'flat'. The default behaviour is for Nova to use qcow2.

#### `openstack-origin`

States the software sources. A common value is an OpenStack UCA release (e.g.
'cloud:bionic-train' or 'cloud:focal-wallaby'). See [Ubuntu Cloud
Archive][wiki-uca]. The underlying host's existing apt sources will be used if
this option is not specified (this behaviour can be explicitly chosen by using
the value of 'distro').

#### `pool-type`

Dictates the Ceph storage pool type. See sections [Ceph pool
type][anchor-ceph-pool-type] and [RBD Nova images][anchor-rbd-nova-images] for
more information.

## Ceph pool type

Ceph storage pools can be configured to ensure data resiliency either through
replication or by erasure coding. This charm supports both types via the
`pool-type` configuration option, which can take on the values of 'replicated'
and 'erasure-coded'. The default value is 'replicated'.

For this charm, the pool type will be associated with Nova-managed images.

> **Note**: Erasure-coded pools are supported starting with Ceph Luminous.

### Replicated pools

Replicated pools use a simple replication strategy in which each written object
is copied, in full, to multiple OSDs within the cluster.

The `ceph-osd-replication-count` option sets the replica count for any object
stored within the 'nova' rbd pool. Increasing this value increases data
resilience at the cost of consuming more real storage in the Ceph cluster. The
default value is '3'.

> **Important**: The `ceph-osd-replication-count` option must be set prior to
  adding the relation to the ceph-mon application. Otherwise, the pool's
  configuration will need to be set by interfacing with the cluster directly.

### Erasure coded pools

Erasure coded pools use a technique that allows for the same resiliency as
replicated pools, yet reduces the amount of space required. Written data is
split into data chunks and error correction chunks, which are both distributed
throughout the cluster.

> **Note**: Erasure coded pools require more memory and CPU cycles than
  replicated pools do.

When using erasure coding two pools will be created: a replicated pool (for
storing RBD metadata) and an erasure coded pool (for storing the data written
into the RBD). The `ceph-osd-replication-count` configuration option only
applies to the metadata (replicated) pool.

Erasure coded pools can be configured via options whose names begin with the
`ec-` prefix.

> **Important**: It is strongly recommended to tailor the `ec-profile-k` and
  `ec-profile-m` options to the needs of the given environment. These latter
  options have default values of '1' and '2' respectively, which result in the
  same space requirements as those of a replicated pool.

See [Ceph Erasure Coding][cdg-ceph-erasure-coding] in the [OpenStack Charms
Deployment Guide][cdg] for more information.

## Ceph BlueStore compression

This charm supports [BlueStore inline compression][ceph-bluestore-compression]
for its associated Ceph storage pool(s). The feature is enabled by assigning a
compression mode via the `bluestore-compression-mode` configuration option. The
default behaviour is to disable compression.

The efficiency of compression depends heavily on what type of data is stored
in the pool and the charm provides a set of configuration options to fine tune
the compression behaviour.

> **Note**: BlueStore compression is supported starting with Ceph Mimic.

## Deployment

These deployment instructions assume that the following applications are
present: glance, nova-cloud-controller, ovn-chassis, and rabbitmq-server.
Storage backends used for VM disks and volumes are configured separately (see
sections [Ceph backed storage][anchor-ceph-backed-storage] and [Local Cinder
storage][anchor-local-cinder-storage].

Let file `nova-compute.yaml` contain the deployment configuration:

```yaml
    nova-compute:
      config-flags: default_ephemeral_format=ext4
      enable-live-migration: true
      enable-resize: true
      migration-auth-type: ssh
      openstack-origin: cloud:focal-wallaby
```

To deploy nova-compute to machine '5':

    juju deploy --to 5 --config nova-compute.yaml nova-compute
    juju add-relation nova-compute:image-service glance:image-service
    juju add-relation nova-compute:cloud-compute nova-cloud-controller:cloud-compute
    juju add-relation nova-compute:neutron-plugin ovn-chassis:nova-compute
    juju add-relation nova-compute:amqp rabbitmq-server:amqp

### Ceph backed storage

Two concurrent Ceph backends are supported: RBD Nova images and RBD Cinder
volumes. Each backend uses its own set of cephx credentials.

The steps below assume a pre-existing Ceph cluster (see the
[ceph-mon][ceph-mon-charm] and [ceph-osd][ceph-osd-charm] charms).

#### RBD Nova images

RBD Nova images are enabled by setting option `libvirt-image-backend` to 'rbd'
and by adding a relation to the Ceph cluster:

    juju config nova-compute libvirt-image-backend=rbd
    juju add-relation nova-compute:ceph ceph-mon:client

> **Warning**: Changing the value of option `libvirt-image-backend` will orphan
  any disks that were set up under a different setting. This will cause the
  restarting of associated VMs to fail.

This solution will place both root and ephemeral disks in Ceph.

> **Pro tip**: An alternative is to selectively store just root disks in Ceph
  by using Cinder as an intermediary. See section [RBD Cinder
  volumes][anchor-rbd-cinder] as well as [Launch an instance from a
  volume][upstream-volume-boot] in the Nova documentation.

#### RBD Cinder volumes

RBD Cinder volumes are enabled by adding a relation to Cinder via the
cinder-ceph application. Assuming Cinder is already backed by Ceph (see the
[cinder-ceph][cinder-ceph-charm] charm):

    juju add-relation nova-compute:ceph-access cinder-ceph:ceph-access

> **Note**: The `nova-compute:ceph-access` relation is not needed for OpenStack
  releases older than Ocata.

### Local Cinder storage

To use local storage, Cinder will need to be configured to use local block
devices. See the [cinder][cinder-charm] charm for details.

## Availability Zones

Nova AZs can be matched with MAAS zones depending on how options
`default-availability-zone` and `customize-failure-domain` are configured. See
[Availability Zones][cdg-ha-az] in the [OpenStack Charms Deployment Guide][cdg]
for in-depth coverage of how this works.

## SSH keys and VM migration

VM migration requires the sharing of public SSH keys (host and several select
users) among the compute hosts. By design, only those hosts belonging to the
same application group will get each other's keys. This means that VM migration
cannot occur (without manual intervention) between hosts belonging to different
groups.

> **Note:** The policy of only sharing SSH keys amongst hosts of the same
  application group may be struck down. This is being tracked in bug [LP
  #1468871][lp-bug-1468871].

## NFV support

This charm (in conjunction with the nova-cloud-controller and neutron-api
charms) supports NFV for Compute nodes that are deployed in Telco NFV
environments.

For more information on NFV see the [Network Functions Virtualization
(NFV)][cdg-nfv] page in the [OpenStack Charms Deployment Guide][cdg].

## Network spaces

This charm supports the use of Juju [network spaces][juju-docs-spaces] (Juju
`v.2.0`). This feature optionally allows specific types of the application's
network traffic to be bound to subnets that the underlying hardware is
connected to.

> **Note**: Spaces must be configured in the backing cloud prior to deployment.

In addition this charm declares two extra-bindings:

* `internal`: used to determine the network space to use for console access to
  instances.

* `migration`: used to determine which network space should be used for live
  and cold migrations between hypervisors.

Note that the nova-cloud-controller application must have bindings to the same
network spaces used for both 'internal' and 'migration' extra bindings.

## Scaling back

Scaling back the nova-compute application implies the removal of one or more
compute nodes. This is documented as a cloud operation in the [OpenStack Charms
Deployment Guide][cdg]. See [Remove a Compute
node][cdg-ops-scale-in-nova-compute].

## Actions

This section lists Juju [actions][juju-docs-actions] supported by the charm.
Actions allow specific operations to be performed on a per-unit basis. To
display action descriptions run `juju actions nova-compute`. If the charm is
not deployed then see file `actions.yaml`.

* `disable`
* `enable`
* `hugepagereport`
* `instance-count`
* `list-compute-nodes`
* `node-name`
* `openstack-upgrade`
* `pause`
* `register-to-cloud`
* `remove-from-cloud`
* `resume`
* `security-checklist`

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-nova-compute].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[juju-docs-actions]: https://jaas.ai/docs/actions
[juju-docs-spaces]: https://juju.is/docs/spaces
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[lp-bugs-charm-nova-compute]: https://bugs.launchpad.net/charm-nova-compute/+filebug
[cdg-install-openstack]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/install-openstack.html
[cloud-archive-ceph]: https://wiki.ubuntu.com/OpenStack/CloudArchive#Ceph_and_the_UCA
[wiki-uca]: https://wiki.ubuntu.com/OpenStack/CloudArchive
[cdg-ceph-erasure-coding]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-erasure-coding.html
[ceph-bluestore-compression]: https://docs.ceph.com/en/latest/rados/configuration/bluestore-config-ref/#inline-compression
[cdg-ops-scale-in-nova-compute]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/ops-scale-in-nova-compute.html
[cdg-nfv]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/nfv.html
[cdg-ironic]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/ironic.html
[cinder-charm]: https://jaas.ai/cinder
[cinder-ceph-charm]: https://jaas.ai/cinder-ceph
[ceph-mon-charm]: https://jaas.ai/ceph-mon
[ceph-osd-charm]: https://jaas.ai/ceph-osd
[upstream-compute]: https://docs.openstack.org/nova/
[cdg-ha-az]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#availability-zones
[anchor-az]: #availability-zones
[anchor-ceph-pool-type]: #ceph-pool-type
[anchor-ceph-backed-storage]: #ceph-backed-storage
[anchor-local-cinder-storage]: #local-cinder-storage
[anchor-rbd-nova-images]: #rbd-nova-images
[anchor-rbd-cinder]: #rbd-cinder-volumes
[upstream-volume-boot]: https://docs.openstack.org/nova/latest/user/launch-instance-from-volume.html
[lp-bug-1468871]: https://bugs.launchpad.net/charms/+source/nova-cloud-controller/+bug/1468871
