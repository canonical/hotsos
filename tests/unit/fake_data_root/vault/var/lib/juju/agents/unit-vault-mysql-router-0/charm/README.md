# Overview

The mysql-router charm provides a [MySQL 8 Router][upstream-mysql8-router]; it
proxies database requests from a principle application to a MySQL 8 InnoDB
Cluster. MySQL Router handles cluster communication and understands the cluster
schema.

It is a subordinate charm that is used in conjunction with the
[mysql-innodb-cluster][mysql-innodb-cluster-charm] charm. It is also used with
a principle charm that supports the 'mysql-shared' interface. The current list
of such charms can be obtained from the [Charm
Store][charms-requires-mysql-shared] (the charms officially supported by the
OpenStack Charms project are published by 'openstack-charmers').

> **Important**: The eoan series is the first series supported by the
  mysql-innodb-cluster and mysql-router charms. These charms replace the
  [percona-cluster][percona-cluster-charm] charm starting with the focal
  series.

# Usage

The charm is deployed as a subordinate to a principle application and then
related to the central mysql-innodb-cluster application:

    principle charm A <---> mysql-router A <--->
    principle charm B <---> mysql-router B <---> mysql-innodb-cluster
    principle charm C <---> mysql-router C <--->

## Configuration

See file `config.yaml` for the full list of configuration options, along with
their descriptions and default values.

## Deployment

To deploy a MySQL 8 Router for joining, say, Keystone to the cloud database:

    juju deploy mysql-router keystone-mysql-router

> **Note**: The mysql-router application is typically given a name that
  corresponds to the associated principle application.

Add a relation to the principle application (via the [shared-db][shared-db]
endpoint):

    juju add-relation keystone:shared-db keystone-mysql-router:shared-db

Then add a relation to the mysql-innodb-cluster application (via the
[db-router][db-router] endpoint):

    juju add-relation keystone-msyql-router:db-router mysql-innodb-cluster:db-router

> **Important**: When network spaces are used, the mysql-router and
  mysql-innodb-cluster charms must be configured such that the 'db-router'
  endpoint is bound to the same space.

Scale out is accomplished by adding units to the principle application:

    juju add-unit keystone

> **Note**: If more than one mysql-router application is placed on the same
  machine the `base-port` configuration option is needed to ensure
  non-conflicting TCP port numbers are used (the default is '3306').

## Actions

This section lists Juju [actions][juju-docs-actions] supported by the charm.
Actions allow specific operations to be performed on a per-unit basis. To
display action descriptions run `juju actions --schema mysql-router`. If the
charm is not deployed then see file `actions.yaml`.

* `stop-mysqlrouter`
* `start-mysqlrouter`
* `restart-mysqlrouter`

# Documentation

The OpenStack Charms project maintains two documentation guides:

* [OpenStack Charm Guide][cg]: for project information, including development
  and support notes
* [OpenStack Charms Deployment Guide][cdg]: for charm usage information

# Bugs

Please report bugs on [Launchpad][lp-bugs-charm-mysql-router].

<!-- LINKS -->

[cg]: https://docs.openstack.org/charm-guide
[cdg]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide
[lp-bugs-charm-mysql-router]: https://bugs.launchpad.net/charm-mysql-router/+filebug
[juju-docs-actions]: https://jaas.ai/docs/actions
[percona-cluster-charm]: https://jaas.ai/percona-cluster
[mysql-router-charm]: https://jaas.ai/mysql-router
[mysql-innodb-cluster-charm]: https://jaas.ai/mysql-innodb-cluster
[upstream-mysql8-router]: https://dev.mysql.com/doc/mysql-router/8.0/en/
[db-router]: https://github.com/openstack-charmers/charm-interface-mysql-router
[shared-db]: https://github.com/openstack/charm-interface-mysql-shared
[cdg-app-ha-mysql8]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ha.html#mysql-8
[charms-requires-mysql-shared]: https://jaas.ai/search?requires=mysql-shared
