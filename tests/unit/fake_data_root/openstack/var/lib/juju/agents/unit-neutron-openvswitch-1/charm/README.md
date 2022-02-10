# Overview

This subordinate charm provides the Neutron OpenvSwitch configuration for a compute node.

Once deployed it takes over the management of the Neutron base and plugin configuration on the compute node.

# Usage

To deploy (partial deployment of linked charms only):

    juju deploy rabbitmq-server
    juju deploy neutron-api
    juju deploy nova-compute
    juju deploy neutron-openvswitch
    juju add-relation neutron-openvswitch nova-compute
    juju add-relation neutron-openvswitch neutron-api
    juju add-relation neutron-openvswitch rabbitmq-server

Note that the rabbitmq-server can optionally be a different instance of the rabbitmq-server charm than used by OpenStack Nova:

    juju deploy rabbitmq-server rmq-neutron
    juju add-relation neutron-openvswitch rmq-neutron
    juju add-relation neutron-api rmq-neutron

The neutron-api and neutron-openvswitch charms must be related to the same instance of the rabbitmq-server charm.

# Restrictions

It should only be used with OpenStack Icehouse and above and requires a separate neutron-api service to have been deployed.

# Disabling security group management

WARNING: this feature allows you to effectively disable security on your cloud!

This charm has a configuration option to allow users to disable any per-instance security group management; this must used with neutron-security-groups enabled in the neutron-api charm and could be used to turn off security on selected set of compute nodes:

    juju deploy neutron-openvswitch neutron-openvswitch-insecure
    juju config neutron-openvswitch-insecure disable-security-groups=True prevent-arp-spoofing=False
    juju deploy nova-compute nova-compute-insecure
    juju add-relation nova-compute-insecure neutron-openvswitch-insecure
    ...

These compute nodes could then be accessed by cloud users via use of host aggregates with specific flavors to target instances to hypervisors with no per-instance security.

# Network Spaces support

This charm supports the use of Juju Network Spaces, allowing the charm to be bound to network space configurations managed directly by Juju.  This is only supported with Juju 2.0 and above.

Open vSwitch endpoints can be configured using the 'data' extra-binding, ensuring that tunnel traffic is routed across the correct host network interfaces:

    juju deploy neutron-openvswitch --bind "data=data-space"

alternatively these can also be provided as part of a juju native bundle configuration:

    neutron-openvswitch:
      charm: cs:xenial/neutron-openvswitch
      bindings:
        data: data-space

NOTE: Spaces must be configured in the underlying provider prior to attempting to use them.

NOTE: Existing deployments using os-data-network configuration options will continue to function; this option is preferred over any network space binding provided if set.

# DPDK fast packet processing support

For OpenStack Mitaka running on Ubuntu 16.04, it's possible to use experimental DPDK userspace network acceleration with Open vSwitch and OpenStack.

Currently, this charm supports use of DPDK enabled devices in bridges supporting connectivity to provider networks.

To use DPDK, you'll need to have supported network cards in your server infrastructure (see [dpdk-nics][DPDK documentation]);  DPDK must be enabled and configured during deployment of the charm, for example:

    neutron-openvswitch:
        enable-dpdk: True
        data-port: "br-phynet1:a8:9d:21:cf:93:fc br-phynet2:a8:9d:21:cf:93:fd br-phynet3:a8:9d:21:cf:93:fe"

As devices are not typically named consistently across servers, multiple instances of each bridge -> mac address mapping can be provided; the charm deals with resolution of the set of bridge -> port mappings that are required for each individual unit of the charm.

DPDK requires the use of hugepages, which is not directly configured in the neutron-openvswitch charm; Hugepage configuration can either be done by providing kernel boot command line options for individual servers using MAAS or using the 'hugepages' configuration option of the nova-compute charm:

    nova-compute:
        hugepages: 50%

By default, the charm will configure Open vSwitch/DPDK to consume a processor core + 1G of RAM from each NUMA node on the unit being deployed; this can be tuned using the dpdk-socket-memory and dpdk-socket-cores configuration options of the charm.  The userspace kernel driver can be configured using the dpdk-driver option.  See config.yaml for more details.

**NOTE:** Changing dpdk-socket-\* configuration options will trigger a restart of Open vSwitch, which currently causes connectivity to running instances to be lost - connectivity can only be restored with a stop/start of each instance.

**NOTE:** Enabling DPDK support automatically disables security groups for instances.

[dpdk-nics]: http://dpdk.org/doc/nics

# DPDK bonding

For deployments using Open vSwitch 2.6.0 or later (OpenStack Ocata on Ubuntu 16.04 onwards), it's also possible to use native Open vSwitch DPDK bonding to provide increased resilience for DPDK based deployments.

This feature is configured using the `dpdk-bond-mappings` and `dpdk-bond-config` options of this charm, for example:

    neutron-openvswitch:
        enable-dpdk: True
        data-port: "br-phynet1:dpdk-bond0"
        dpdk-bond-mappings: "dpdk-bond0:a8:9d:21:cf:93:fc dpdk-bond0:a8:9d:21:cf:93:fd"
        dpdk-bond-config: ":balance-slb:off:fast"

In this example, the PCI devices associated with the two MAC addresses provided will be configured as an OVS DPDK bond device named `dpdk-bond0`; this bond device is then used in br-phynet1 to provide resilient connectivity to the underlying network fabric.

The charm will automatically detect which PCI devices are on each unit of the application based on the `dpdk-bond-mappings` configuration provided, supporting use in environments where network device naming may not be consistent across units.

# Port Configuration

> **Note**: External port configuration only applies when DVR mode is enabled.
  This may not work when `neutron-openvswitch` is deployed in a LXD container.
  If your deployment requires mixed placement of `neutron-openvswitch` units,
  add multiple application instances with different names to your model to
  allow for separate configuration. You can view examples of this configuration
  in the [Octavia Charm](https://jaas.ai/octavia) functional test gate
  [bundles](https://opendev.org/openstack/charm-octavia/src/branch/master/src/tests/bundles).

All network types (internal, external) are configured with bridge-mappings and
data-port and the flat-network-providers configuration option of the
neutron-api charm.  Once deployed, you can configure the network specifics
using neutron net-create.

If the device name is not consistent between hosts, you can specify the same
bridge multiple times with MAC addresses instead of interface names.  The charm
will loop through the list and configure the first matching interface.

Basic configuration of a single external network, typically used as floating IP
addresses combined with a GRE private network:

    neutron-openvswitch:
        bridge-mappings:         physnet1:br-ex
        data-port:               br-ex:eth1
    neutron-api:
        flat-network-providers:  physnet1

    neutron net-create --provider:network_type flat \
        --provider:physical_network physnet1 --router:external=true \
        external
    neutron router-gateway-set provider external

Alternative configuration with two networks, where the internal private
network is directly connected to the gateway with public IP addresses but a
floating IP address range is also offered.

    neutron-openvswitch:
        bridge-mappings:         physnet1:br-data external:br-ex
        data-port:               br-data:eth1 br-ex:eth2
    neutron-api:
        flat-network-providers:  physnet1 external

Alternative configuration with two external networks, one for public instance
addresses and one for floating IP addresses.  Both networks are on the same
physical network connection (but they might be on different VLANs, that is
configured later using neutron net-create).

    neutron-openvswitch:
        bridge-mappings:         physnet1:br-data
        data-port:               br-data:eth1
    neutron-api:
        flat-network-providers:  physnet1

    neutron net-create --provider:network_type vlan \
        --provider:segmentation_id 400 \
        --provider:physical_network physnet1 --shared external
    neutron net-create --provider:network_type vlan \
        --provider:segmentation_id 401 \
        --provider:physical_network physnet1 --shared --router:external=true \
        floating
    neutron router-gateway-set provider floating

This replaces the previous system of using ext-port, which always created a bridge
called br-ex for external networks which was used implicitly by external router
interfaces.

Note: If data-port is specified, the value of ext-port is ignored. This
prevents misconfiguration of the charm. Aditionaly, in this scenario an error
message is logged and the unit is marked as blocked in order to notify about
the misconfiguration.

# Deferred service events

Operational or maintenance procedures applied to a cloud often lead to the
restarting of various OpenStack services and/or the calling of certain charm
hooks. Although normal, such events can be undesirable due to the service
interruptions they can cause.

The deferred service events feature provides the operator the choice of
preventing these service restarts and hook calls from occurring, which can then
be resolved at a more opportune time.

See the [Deferred service events][cdg-deferred-service-events] page in the
[OpenStack Charms Deployment Guide][cdg] for an in-depth treatment of this
feature.

<!-- LINKS -->

[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[cdg-deferred-service-events]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/deferred-events.html
