Plugins
=======

Hotsos supports the following plugins to cover common cloud applications as well as core system areas:

 * `juju <https://juju.is/>`_
 * kernel
 * `kubernetes <https://kubernetes.io/>`_
 * `lxd <https://linuxcontainers.org/lxd/>`_
 * `maas <https://maas.io/>`_
 * `mysql <https://dev.mysql.com/doc/refman/8.0/en/mysql-innodb-cluster-introduction.html>`_
 * `openstack <https://www.openstack.org/>`_
 * `openvswitch <https://www.openvswitch.org/>`_ (includes ovn)
 * `rabbitmq <https://www.rabbitmq.com/>`_
 * `sosreport <https://github.com/sosreport/sos>`_
 * storage (includes ceph, bcache)
 * system
 * `vault <https://www.vaultproject.io/>`_

Core Library
============

The implementation of plugins is split in two such that re-usable library code is kept in the `core plugin <https://github.com/canonical/hotsos/tree/main/hotsos/core/plugins>`_ code and everything else is treated as a :ref:`extension<Plugin Extensions>`.

Plugin Extensions
=================

These is where the output summary is generated and also provides a space to extend core plugin functionality to generate additional output e.g.
using :ref:`events`.

