Core Library
============

The implementation of plugins is split in two such that re-usable library code is kept in the `core plugin <https://github.com/canonical/hotsos/tree/main/hotsos/core/plugins>`_ code and everything else is treated as a `plugin extension <https://github.com/canonical/hotsos/tree/main/hotsos/plugin_extensions>`_.

Plugins
-------

Hotsos supports the following plugins to cover common cloud applications as well as core system areas:

* `juju <https://juju.is/>`_
* `kernel <https://ubuntu.com/kernel>`_
* `kubernetes <https://kubernetes.io/>`_
* `lxd <https://canonical.com/lxd>`_
* `maas <https://maas.io/>`_
* `microcloud <https://canonical.com/microcloud>`_
* `mysql <https://dev.mysql.com/doc/refman/8.0/en/mysql-innodb-cluster-introduction.html>`_
* `openstack <https://www.openstack.org/>`_
* `openvswitch <https://www.openvswitch.org/>`_ (includes `ovn <https://www.ovn.org/en/>`_)
* `rabbitmq <https://www.rabbitmq.com/>`_
* `sosreport <https://github.com/sosreport/sos>`_
* storage (includes `ceph <https://ceph.com/en/>`_, `bcache <https://docs.kernel.org/admin-guide/bcache.html>`_)
* system
* `vault <https://www.vaultproject.io/>`_

Plugin Extensions
-----------------

These is where the output summary is generated and also provides a space to extend core plugin functionality to generate additional output e.g.
using :ref:`Events<events overview>`.

Defs
====

All scenario and event implementations.


Unit Tests
==========

Python unit tests for all code.
