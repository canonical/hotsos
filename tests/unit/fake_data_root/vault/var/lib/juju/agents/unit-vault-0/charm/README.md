# Overview

The vault charm deploys [Vault][vault-upstream], a tool for securely managing
secrets used in modern computing (e.g. passwords, certificates, API keys).
Charmed OpenStack employs Vault to handle TLS certificates, allowing for a
centrally managed solution for the encryption of API services across the cloud.
Vault is also commonly used to implement [Encryption at Rest][cdg-encryption]
on Charmed OpenStack.

The charm installs Vault from a [snap][snap-upstream].

> **Important**: Vault is a requirement for the OVN charms.

# Usage

## Configuration

This section covers common and/or important configuration options. See file
`config.yaml` for the full list of options, along with their descriptions and
default values. See the [Juju documentation][juju-docs-config-apps] for details
on configuring applications.

#### `channel`

The `channel` option sets the snap channel to use for deployment (e.g.
'latest/edge'). The default value is 'latest/stable'.

## Deployment

> **Important**: Some steps must be performed after deployment. Section
  'Post-deployment tasks' covers this.

Vault is often containerised. Here a single unit is deployed to a new
container on machine '1':

    juju deploy --to lxd:1 vault

> **Note**: When Vault is deployed to metal or to a KVM guest the charm will
  enable mlock (memory locking) to prevent secrets from being saved to disk via
  page swapping. The mlock feature is not available to containers.

Now connect the vault application to an existing database. This can be the
cloud's database or a separate, dedicated database.

Some database applications are influenced by the series. Prior to focal
[percona-cluster][percona-cluster-charm] is used, otherwise it is replaced by
[mysql-innodb-cluster][mysql-innodb-cluster-charm]. The
[postgresql][postgresql-charm] application can also be used.

For percona-cluster:

    juju add-relation vault:shared-db percona-cluster:shared-db

For mysql-innodb-cluster:

    juju deploy mysql-router vault-mysql-router
    juju add-relation vault-mysql-router:db-router mysql-innodb-cluster:db-router
    juju add-relation vault-mysql-router:shared-db vault:shared-db

For postgresql:

    juju add-relation vault:db postgresql:db

> **Note**: For PostgreSQL, its version and the underlying machine series must
  be compatible (e.g. 9.5/xenial or 10/bionic). The postgresql charm's
  configuration option `version` is used to select a version at deploy time.

## TLS

Communication with the Vault REST API can be encrypted with TLS. This is
configured with the following charm configuration options:

* `ssl-ca`
* `ssl-cert`
* `ssl-chain`
* `ssl-key`

> **Note**: The process of encrypting the Vault API is separate from that of
 using Vault to manage the encryption of OpenStack API services. See [Managing
 TLS certificates][cdg-vault-certs] in the [OpenStack Charms Deployment
  Guide][cdg] for details.

## Post-deployment tasks

Once the application is deployed the following tasks **must** be performed:

* Vault initialisation
* Unsealing of Vault
* Charm authorisation

Vault itself will be needed as a client to perform these tasks.

### Vault client

Vault is needed as a client in order to manage the Vault deployment. Install it
on the host where the Juju client resides:

    sudo snap install vault

### Initialise Vault

Identify the vault unit by setting the ``VAULT_ADDR`` environment variable
based on the IP address of the unit. This can be discovered from `juju status`
output (column 'Public address'). Here we'll use '10.0.0.126':

    export VAULT_ADDR="http://10.0.0.126:8200"

Initialise Vault by specifying the number of unseal keys that should get
generated as well as the number of unseal keys that are needed in order to
complete the unseal process. Below we will specify five and three,
respectively:

    vault operator init -key-shares=5 -key-threshold=3

Sample output:

    Unseal Key 1: XONSc5Ku8HJu+ix/zbzWhMvDTiPpwWX0W1X/e/J1Xixv
    Unseal Key 2: J/fQCPvDeMFJT3WprfPy17gwvyPxcvf+GV751fTHUoN/
    Unseal Key 3: +bRfX5HMISegsODqNZxvNcupQp/kYQuhsQ2XA+GamjY4
    Unseal Key 4: FMRTPJwzykgXFQOl2XTupw2lfgLOXbbIep9wgi9jQ2ls
    Unseal Key 5: 7rrxiIVQQWbDTJPMsqrZDKftD6JxJi6vFOlyC0KSabDB

    Initial Root Token: s.ezlJjFw8ZDZO6KbkAkm605Qv

    Vault initialized with 5 key shares and a key threshold of 3. Please securely
    distribute the key shares printed above. When the Vault is re-sealed,
    restarted, or stopped, you must supply at least 3 of these keys to unseal it
    before it can start servicing requests.

    Vault does not store the generated master key. Without at least 3 key to
    reconstruct the master key, Vault will remain permanently sealed!

    It is possible to generate new unseal keys, provided you have a quorum of
    existing unseal keys shares. See "vault operator rekey" for more information.

Besides displaying the five unseal keys the output also includes an "initial
root token". This token is used to access the Vault API.

> **Warning**: It is not possible to unseal Vault without the unseal keys, nor
  is it possible to manage Vault without the initial root token. **Store this
  information in a safe place immediately**.

### Unseal Vault

Unseal the vault unit using the requisite number of unique keys (three in this
example):

    vault operator unseal XONSc5Ku8HJu+ix/zbzWhMvDTiPpwWX0W1X/e/J1Xixv
    vault operator unseal FMRTPJwzykgXFQOl2XTupw2lfgLOXbbIep9wgi9jQ2ls
    vault operator unseal 7rrxiIVQQWbDTJPMsqrZDKftD6JxJi6vFOlyC0KSabDB

In an HA environment repeat the unseal process for each unit. Prior to
unsealing a unit change the value of the ``VAULT_ADDR`` variable so that it
points to that unit.

> **Note**: Maintenance work on the cloud may require vault units to be paused
  and later resumed. A resumed vault unit will be sealed and will therefore
  require unsealing. See [Managing power events][cdg-power-events] in the
  [OpenStack Charms Deployment Guide][cdg] for details.

Proceed to the next step once all units have been unsealed.

### Authorise the vault charm

The vault charm must be authorised to access the Vault deployment in order to
create storage backends (for secrets) and roles (to allow other applications to
access Vault for encryption key storage).

Generate a root token with a limited lifetime (10 minutes here) using the
initial root token:

    export VAULT_TOKEN=s.ezlJjFw8ZDZO6KbkAkm605Qv
    vault token create -ttl=10m

Sample output:

    Key                  Value
    ---                  -----
    token                s.QMhaOED3UGQ4MeH3fmGOpNED
    token_accessor       nApB972Dp2lnTTIF5VXQqnnb
    token_duration       10m
    token_renewable      true
    token_policies       ["root"]
    identity_policies    []
    policies             ["root"]

This temporary token ('token') is then used to authorise the charm:

    juju run-action --wait vault/leader authorize-charm token=s.QMhaOED3UGQ4MeH3fmGOpNED

After the action completes execution, the vault unit(s) will become active and
any pending requests for secrets storage will be processed for consuming
applications.

Here is sample status output for an unsealed three-unit Vault cluster:

    vault/0*                 active    idle   0/lxd/1  10.0.0.126      8200/tcp  Unit is ready (active: false, mlock: disabled)
      vault-hacluster/0*     active    idle            10.0.0.126                Unit is ready and clustered
      vault-mysql-router/0*  active    idle            10.0.0.126                Unit is ready
    vault/1                  active    idle   1/lxd/1  10.0.0.130      8200/tcp  Unit is ready (active: true, mlock: disabled)
      vault-hacluster/2      active    idle            10.0.0.130                Unit is ready and clustered
      vault-mysql-router/2   active    idle            10.0.0.130                Unit is ready
    vault/2                  active    idle   2/lxd/1  10.0.0.132      8200/tcp  Unit is ready (active: false, mlock: disabled)
      vault-hacluster/1      active    idle            10.0.0.132                Unit is ready and clustered
      vault-mysql-router/1   active    idle            10.0.0.132                Unit is ready

Now that the post-deployment steps have been completed you will most likely
want to add a CA certificate to Vault. See [Managing TLS
certificates][cdg-vault-certs-add] in the [OpenStack Charms Deployment
Guide][cdg] for details.

## Actions

This section lists Juju [actions][juju-docs-actions] supported by the charm.
Actions allow specific operations to be performed on a per-unit basis.

* `authorize-charm`
* `disable-pki`
* `generate-root-ca`
* `get-csr`
* `get-root-ca`
* `pause`
* `refresh-secrets`
* `reissue-certificates`
* `resume`
* `upload-signed-csr`
* `reload`
* `restart`

To display action descriptions run `juju actions --schema vault`. If the charm
is not deployed then see file `actions.yaml`.

## High availability

When more than one unit is deployed with the [hacluster][hacluster-charm]
application the charm will bring up an HA active/active cluster.

There are two mutually exclusive high availability options: using virtual IP(s)
or DNS. In both cases the hacluster subordinate charm is used to provide the
Corosync and Pacemaker backend HA functionality.

In addition, HA Vault will require the etcd and easyrsa applications.

See [Infrastructure high availability][cdg-ha-apps] in the [OpenStack Charms
Deployment Guide][cdg] for details.

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-vault].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/
[lp-bugs-charm-vault]: https://bugs.launchpad.net/vault-charm/+filebug
[juju-docs-actions]: https://jaas.ai/docs/actions
[snap-upstream]: https://snapcraft.io/
[hacluster-charm]: https://jaas.ai/hacluster
[vault-charm]: https://jaas.ai/vault
[percona-cluster-charm]: https://jaas.ai/percona-cluster
[mysql-innodb-cluster-charm]: https://jaas.ai/mysql-innodb-cluster
[postgresql-charm]: https://jaas.ai/postgresql
[vault-upstream]: https://www.vaultproject.io/docs/what-is-vault/
[cdg-vault-certs]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-certificate-management.html
[cdg-vault-certs-add]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-certificate-management.html#add-a-ca-certificate
[cdg-ha-apps]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#ha-applications
[juju-docs-config-apps]: https://juju.is/docs/configuring-applications
[cdg-power-events]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-managing-power-events.html#vault
[cdg-encryption]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-encryption-at-rest.html
