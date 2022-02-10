# Overview

[Ceph][ceph-upstream] is a unified, distributed storage system designed for
excellent performance, reliability, and scalability.

The ceph-osd charm deploys the Ceph object storage daemon (OSD) and manages its
volumes. It is used in conjunction with the [ceph-mon][ceph-mon-charm] charm.
Together, these charms can scale out the amount of storage available in a Ceph
cluster.

# Usage

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. A YAML file (e.g. `ceph-osd.yaml`) is often used to store
configuration options. See the [Juju documentation][juju-docs-config-apps] for
details on configuring applications.

#### `bluestore`

The `bluestore` option specifies whether the
[BlueStore][upstream-ceph-bluestore] storage backend is used for all OSD
devices. The feature is enabled by default (value 'True'). If set to 'True',
this option overrides the `osd-format` option as BlueStore does not use a
traditional filesystem.

> **Important**: This option has no effect unless Ceph Luminous (or greater) is
  in use.

#### `customize-failure-domain`

The `customize-failure-domain` option determines how a Ceph CRUSH map is
configured.

A value of 'false' (the default) will lead to a map that will replicate data
across hosts (implemented as [Ceph bucket type][upstream-ceph-buckets] 'host').
With a value of 'true' all MAAS-defined zones will be used to generate a map
that will replicate data across Ceph availability zones (implemented as bucket
type 'rack').

This option is also supported by the ceph-mon charm. Its value must be the same
for both charms.

#### `osd-devices`

The `osd-devices` option lists what block devices can be used for OSDs across
the cluster. See section 'Storage devices' for an elaboration on this
fundamental topic.

#### `osd-format`

The `osd-format` option specifies what filesystem to use for all OSD devices
('xfs' or 'ext4'). The default value is 'xfs'. This option only applies when
Ceph Luminous (or greater) is in use and option `bluestore` is set to 'False'.

#### `source`

The `source` option states the software sources. A common value is an OpenStack
UCA release (e.g. 'cloud:xenial-queens' or 'cloud:bionic-ussuri'). See [Ceph
and the UCA][cloud-archive-ceph]. The underlying host's existing apt sources
will be used if this option is not specified (this behaviour can be explicitly
chosen by using the value of 'distro').

### Storage devices

A storage device is destined as an OSD (Object Storage Device). There can be
multiple OSDs per storage node (ceph-osd unit).

The list of all possible storage devices for the cluster is defined by the
`osd-devices` option. The below examples can be used in the `ceph-osd.yaml`
configuration file.

Block devices (regular),

    ceph-osd:
      osd-devices: /dev/vdb /dev/vdc /dev/vdd

Each regular block device must be an absolute path to a device node.

Block devices (Juju storage),

    ceph-osd:
      storage:
        osd-devices: cinder,20G

See the [Juju documentation][juju-docs-storage] for guidance on implementing
Juju storage.

Directory-backed OSDs,

    ceph-osd:
      storage:
        osd-devices: /var/tmp/osd-1

> **Note**: OSD directories can no longer be created starting with Ceph
  Nautilus. Existing OSD directories will continue to function after an upgrade
  to Nautilus.

The list defined by option `osd-devices` may affect newly added ceph-osd units
as well as existing units (the option may be modified after units have been
added). The charm will attempt to activate as Ceph storage any listed device
that is visible by the unit's underlying machine. To prevent the activation of
volumes on existing units the `blacklist-add-disk` action may be used.

The configuration option is modified in the usual way. For instance, to have it
consist solely of devices '/dev/sdb' and '/dev/sdc':

    juju config ceph-osd osd-devices='/dev/sdb /dev/sdc'

The charm will go into a blocked state (visible in `juju status` output) if it
detects pre-existing data on a device. In this case the operator can either
instruct the charm to ignore the disk (action `blacklist-add-disk`) or to have
it purge all data on the disk (action `zap-disk`).

> **Important**: The recommended minimum number of OSDs in the cluster is three
  and this is what the ceph-mon charm expects (the cluster will not form with a
  lesser number). See option `expected-osd-count` in the ceph-mon charm to
  overcome this but beware that going below three is not a supported
  configuration.

## Deployment

A cloud with three MON nodes is a typical design whereas three OSDs are
considered the minimum. For example, to deploy a Ceph cluster consisting of
three OSDs (one per ceph-osd unit) and three MONs:

    juju deploy -n 3 --config ceph-osd.yaml ceph-osd
    juju deploy -n 3 --to lxd:0,lxd:1,lxd:2 ceph-mon
    juju add-relation ceph-osd:mon ceph-mon:osd

Here, a containerised MON is running alongside each storage node. We've assumed
that the machines spawned in the first command are assigned IDs of 0, 1, and 2.

> **Note**: Refer to the [Install OpenStack][cdg-install-openstack] page in the
  OpenStack Charms Deployment Guide for instructions on installing the ceph-osd
  application for use with OpenStack.

For each ceph-osd unit, the ceph-osd charm will scan for all the devices
configured via the `osd-devices` option and attempt to assign to it all of the
ones it finds. The cluster's initial pool of available storage is the "sum" of
all these assigned devices.

## Network spaces

This charm supports the use of Juju [network spaces][juju-docs-spaces] (Juju
`v.2.0`). This feature optionally allows specific types of the application's
network traffic to be bound to subnets that the underlying hardware is
connected to.

> **Note**: Spaces must be configured in the backing cloud prior to deployment.

The ceph-osd charm exposes the following Ceph traffic types (bindings):

* 'public' (front-side)
* 'cluster' (back-side)

For example, providing that spaces 'data-space' and 'cluster-space' exist, the
deploy command above could look like this:

    juju deploy --config ceph-osd.yaml -n 3 ceph-osd \
       --bind "public=data-space cluster=cluster-space"

Alternatively, configuration can be provided as part of a bundle:

```yaml
    ceph-osd:
      charm: cs:ceph-osd
      num_units: 1
      bindings:
        public: data-space
        cluster: cluster-space
```

Refer to the [Ceph Network Reference][ceph-docs-network-ref] to learn about the
implications of segregating Ceph network traffic.

> **Note**: Existing ceph-osd units configured with the `ceph-public-network`
  or `ceph-cluster-network` options will continue to honour them. Furthermore,
  these options override any space bindings, if set.

## AppArmor profiles

Although AppArmor is not enabled for Ceph by default, an AppArmor profile can
be generated by the charm by assigning a value of 'complain', 'enforce', or
'disable' (the default) to option `aa-profile-mode`.

> **Caution**: Enabling an AppArmor profile is disruptive to a running Ceph
  cluster as all ceph-osd processes must be restarted.

The new profile has a narrow supported use case, and it should always be
verified in pre-production against the specific configurations and topologies
intended for production.

The profiles generated by the charm should **not** be used in the following
scenarios:

* On any version of Ubuntu older than 16.04
* On any version of Ceph older than Luminous
* When OSD journal devices are in use
* When Ceph BlueStore is enabled

## Block device encryption

The ceph-osd charm supports encryption for OSD volumes that are backed by block
devices. To use Ceph's native key management framework, available since Ceph
Jewel, set option `osd-encrypt` for the ceph-osd charm:

```yaml
    ceph-osd:
      osd-encrypt: True
```

Here, dm-crypt keys are stored in the MON sub-cluster.

Alternatively, since Ceph Luminous, encryption keys can be stored in Vault,
which is deployed and initialised via the [vault][vault-charm] charm. Set
options `osd-encrypt` and `osd-encrypt-keymanager` for the ceph-osd charm:

```yaml
    ceph-osd:
      osd-encrypt: True
      osd-encrypt-keymanager: vault
```

> **Important**: Post deployment configuration will only affect block devices
  associated with **new** ceph-osd units.

## Actions

This section covers Juju [actions][juju-docs-actions] supported by the charm.
Actions allow specific operations to be performed on a per-unit basis. To
display action descriptions run `juju actions --schema ceph-osd`. If the charm
is not deployed then see file `actions.yaml`.

* `add-disk`
* `blacklist-add-disk`
* `blacklist-remove-disk`
* `get-availibility-zone`
* `list-disks`
* `osd-in`
* `osd-out`
* `security-checklist`
* `start`
* `stop`
* `zap-disk`

## Working with OSDs

### Set OSDs to 'out'

Use the `osd-out` action to set OSD volumes on a unit to 'out'.

> **Warning**: This action has the potential of impacting your cluster
  significantly. The [Ceph documentation][ceph-docs-removing-osds] on this
  topic is considered essential reading.

Unless the cluster itself is set to 'noout' this action will cause Ceph to
rebalance data by migrating PGs out of the affected OSDs and onto OSDs
available on other units. The impact is twofold:

1. The available space on the remaining OSDs is reduced. Not only is there less
   space for future workloads but there is a danger of exceeding the cluster's
   storage capacity.
1. The traffic and CPU load on the cluster is increased.

> **Note**: It has been reported that setting OSDs to 'out' may cause some PGs
  to get stuck in the 'active+remapped' state. This is an upstream issue.

The [ceph-mon][ceph-mon-charm] charm has an action called `set-noout` that sets
'noout' for the cluster.

It may be perfectly fine to have data rebalanced. The decisive factor is
whether the OSDs are being paused temporarily (e.g. the underlying machine is
scheduled for maintenance) or whether they are being removed from the cluster
completely (e.g. the storage hardware is reaching EOL).

Examples:

    # Set OSDs '0' and '1' to 'out' on unit `ceph-osd/4`
    juju run-action --wait ceph-osd/4 osd-out osds=osd.0,osd.1

    # Set all OSDs to 'out' on unit `ceph-osd/2`
    juju run-action --wait ceph-osd/2 osd-out osds=all

### Set OSDs to 'in'

Use the `osd-in` action to set OSD volumes on a unit to 'in'.

The `osd-in` action is reciprocal to the `osd-out` action. The OSDs are set to
'in'. It is typically used when the `osd-out` action was used in conjunction
with the cluster 'noout' flag.

Examples:

    # Set OSDs '0' and '1' to 'in' on unit `ceph-osd/4`
    juju run-action --wait ceph-osd/4 osd-in osds=osd.0,osd.1

    # Set all OSDs to 'in' on unit `ceph-osd/2`
    juju run-action --wait ceph-osd/2 osd-in osds=all

### Stop and start OSDs

Use the `stop` and `start` actions to stop and start OSD daemons on a unit.

> **Important**: These actions are not available on the 'trusty' series due to
  the reliance on `systemd`.

Examples:

    # Stop services 'ceph-osd@0' and 'ceph-osd@1' on unit `ceph-osd/4`
    juju run-action --wait ceph-osd/4 stop osds=0,1

    # Start all ceph-osd services on unit `ceph-osd/2`
    juju run-action --wait ceph-osd/2 start osds=all

> **Note**: Stopping an OSD daemon will put the associated unit into a blocked
  state.

## Working with disks

### List disks

Use the `list-disks` action to list disks known to a unit.

The action lists the unit's block devices by categorising them in three ways:

* `disks`: visible (known by udev), unused (not mounted), and not designated as
  an OSD journal (via the `osd-journal` configuration option)

* `blacklist`: like `disks` but blacklisted (see action `blacklist-add-disk`)

* `non-pristine`: like `disks` but not eligible for use due to the presence of
  existing data

Example:

    # List disks on unit `ceph-osd/4`
    juju run-action --wait ceph-osd/4 list-disks

### Add a disk

Use the `add-disk` action to add a disk to a unit.

A ceph-osd unit is automatically assigned OSD volumes based on the current
value of the `osd-devices` application option. The `add-disk` action allows the
operator to manually add OSD volumes (for disks that are not listed by
`osd-devices`) to an existing unit.

**Parameters**

<!-- The next line has two trailing spaces. -->

* `osd-devices` (required)  
  A space-separated list of devices to format and initialise as OSD volumes.

<!-- The next line has two trailing spaces. -->

* `bucket`  
  The name of a Ceph bucket to add these devices to.

Example:

    # Add disk /dev/vde on unit `ceph-osd/4`
    juju run-action --wait ceph-osd/4 add-disk osd-devices=/dev/vde

### Blacklist a disk

Use the `blacklist-add-disk` action to add a disk to a unit's blacklist.

The action allows the operator to add disks (that are visible to the unit's
underlying machine) to the unit's blacklist. A blacklisted device will not be
initialised as an OSD volume when the value of the `osd-devices` application
option changes. This action does not prevent a device from being activated via
the `add-disk` action.

Use the `list-disks` action to list the unit's blacklist entries.

> **Important**: This action and blacklist do not have any effect on current
  OSD volumes.

**Parameters**

<!-- The next line has two trailing spaces. -->

* `osd-devices` (required)  
  A space-separated list of devices to add to a unit's blacklist.

Example:

    # Blacklist disks /dev/vda and /dev/vdf on unit `ceph-osd/0`
    juju run-action --wait ceph-osd/0 \
       blacklist-add-disk osd-devices='/dev/vda /dev/vdf'

### Un-blacklist a disk

Use the `blacklist-remove-disk` action to remove a disk from a unit's
blacklist.

**Parameters**

<!-- The next line has two trailing spaces. -->

* `osd-devices` (required)  
  A space-separated list of devices to remove from a unit's blacklist.

Each device should have an existing entry in the unit's blacklist. Use the
`list-disks` action to list the unit's blacklist entries.

Example:

    # Un-blacklist disk /dev/vdb on unit `ceph-osd/1`
    juju run-action --wait ceph-osd/1 \
       blacklist-remove-disk osd-devices=/dev/vdb

### Zap a disk

Use the `zap-disk` action to purge a disk of all data.

In order to prevent unintentional data loss, the charm will not use a disk that
contains data. To forcibly make a disk available, the `zap-disk` action can be
used. Due to the destructive nature of this action the `i-really-mean-it`
option must be passed. This action is normally followed by the `add-disk`
action.

**Parameters**

<!-- The next line has two trailing spaces. -->

* `devices` (required)  
  A space-separated list of devices to be recycled.

<!-- The next line has two trailing spaces. -->

* `i-really-mean-it` (required)  
  A boolean option for confirming the action.

Example:

    # Zap disk /dev/vdc on unit `ceph-osd/3`
    juju run-action --wait ceph-osd/3 \
       zap-disk i-really-mean-it=true devices=/dev/vdc

> **Note**: The `zap-disk` action cannot be run on a mounted device, an active
  BlueStore device, or an encrypted device. There are also issues with
  LVM-backed volumes (see [LP #1858519][lp-bug-1858519]).

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

See also the [Charmed Ceph documentation][charmed-ceph-docs].

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-ceph-osd].

<!-- LINKS -->

[ceph-upstream]: https://ceph.io
[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[ceph-mon-charm]: https://jaas.ai/ceph-mon
[vault-charm]: https://jaas.ai/vault
[charmed-ceph-docs]: https://ubuntu.com/ceph/docs
[juju-docs-storage]: https://jaas.ai/docs/storage
[juju-docs-actions]: https://jaas.ai/docs/actions
[juju-docs-spaces]: https://jaas.ai/docs/spaces
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[ceph-docs-removing-osds]: https://docs.ceph.com/docs/master/rados/operations/add-or-rm-osds/
[ceph-docs-network-ref]: http://docs.ceph.com/docs/master/rados/configuration/network-config-ref
[lp-bugs-charm-ceph-osd]: https://bugs.launchpad.net/charm-ceph-osd/+filebug
[cdg-install-openstack]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/install-openstack.html
[upstream-ceph-buckets]: https://docs.ceph.com/docs/master/rados/operations/crush-map/#types-and-buckets
[upstream-ceph-bluestore]: https://docs.ceph.com/en/latest/rados/configuration/storage-devices/#bluestore
[cloud-archive-ceph]: https://wiki.ubuntu.com/OpenStack/CloudArchive#Ceph_and_the_UCA
[lp-bug-1858519]: https://bugs.launchpad.net/charm-ceph-osd/+bug/1858519
