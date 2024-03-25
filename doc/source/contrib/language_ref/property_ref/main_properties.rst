Vars
====

Use the ``vars`` property to define one or more variables that can be referenced
from other properties. These are defined as a list of ``key: value`` pairs where
values can either be standard types like str, int, bool e.g.

.. code-block:: yaml

  vars:
    sfoo: foo
    ifoo: 400
    bfoo: true

Or they can reference a Python property. This is done by prefixing the import string with '@' e.g.

.. code-block:: yaml

  vars:
    foo: '@path.to.myproperty'

A :ref:`factory <FactoryClasses>` reference can also be defined using the following form:

.. code-block:: yaml

  vars:
    foo: '@<modpath>.<factoryclassname>.<property>:<input>'

When *$foo* is used it will have the value of *myproperty*.

Accessing
---------

Variables are accessed from other properties by prefixing their name with a '$' e.g.

.. code-block:: yaml

  vars:
    foo: true
  checks:
    foo_is_true:
      requires:
        varops: [[$foo], [eq, true]]

Variables are accessible from any property within the file in which they are defined.

NOTE: global properties are not yet supported.

Checks
======

A dictionary of labelled checks each of which is a grouping of properties (see
Supported Properties). Eack check is executed independently and produces a
boolean result of True or False.

Checks are normally implemented in conjunction with :ref:`Conclusions<conclusions>`
as part of :ref:`Scenarios<scenarios overview>`.

Usage:

.. code-block:: yaml

    checks:
      check1:
        <property1>
      check2:
        <property2>
        <property3>


The following properties are supported:

* :ref:`Input<input>`
* :ref:`Requires<requires>`
* :ref:`Search<search>`

Cache keys:
* search - (if check contains a search property) this is set to the cache of that property.
* num_results - (if check contains a search property) this reflects the number of search results for that search.
* files - (if check contains a search property) this is a list of all files searched.
* requires - (if check contains a requires property) this is set to the cache of that property.

Conclusions
===========

A conclusion is used in :ref:`scenarios` to derive an outcome based on the
result of one or more :ref:`checks <checks>`. When a conclusion is matched,
it raised a bug or issue along with a message descibing the problem identified
as well as providing suggestions on how to handle it. Typically more than one
conclusion is defined and by default all are given priority 1 but this can be
overriden with the *priority* field. The high priority conclusion(s) take
precedence.

The message can optionally use format fields which, if used, require
format-dict to be provided with key/value pairs. The values must be
an importable attribute, property or method.

Usage:

.. code-block:: yaml

    conclusions:
      <name>:
        priority: <int>
        decision:
          and|or: [check1, ...]
        raises:
          type: <import-path>
          message: <formattable string>
          format-dict:
            <key>: <value>


The following provides an explanation of the fields required to define a conclusion:

Decision
--------

This property is typically used in :ref:`Conclusions<conclusions>`.
CHECKS refers to a set of one or more :ref:`Checks<checks>` names organised as a
:ref:`LogicalGroupings` to make a decision based on the outcome of more
checks.

Usage:

.. code-block:: yaml

    decision: CHECKS

Priority
--------

Defines an integer priority. This is a very simple property that is typically
used by :ref:`conclusions` to associate a priority or precedence to
conclusions.

Usage:

.. code-block:: yaml

    priority: <int>

Raises
------

Defines an issue to raise along with the message displayed. For example a
:ref:`Checks<checks>` may want to raise an `issue_types <https://github.com/canonical/hotsos/blob/main/hotsos/core/issues/issue_types.py>`_
with a formatted message where format fields are filled using Python properties
or search results.

Usage:

.. code-block:: yaml

    raises:
      type: <type>
      bug-id: <str>
      message: <str>
      format-dict: <dict>

If *type* is a `bug type <https://github.com/canonical/hotsos/blob/main/hotsos/core/issues/issue_types.py>`_ then a *bug-id*
must be provided.

If the *message* string contains format fields these can be filled
using ```format-dict``` - a dictionary of key/value pairs where *key* matches a
format field in the message string and *value* is either a Python property
import path or a :ref:`property cache reference<PropertyCache>`

Requires
========

Defines a set of one or more :ref:`requirements <requirement types>` to be
executed with a pass/fail result. This property is implemented as a
:ref:`mapped property <mappedproperties>` so the root *requires* name is
optional. For the purposes of examples below we will always use the expanded
format i.e. with the *requires* key.

Usage:

The simplest form contains a single type e.g.:

.. code-block:: yaml

    requires:
      systemd:
        ufw: active
        
This requirement stipulates that a systemd service called ufw must exist and have state active for the result to be True.

A requirement can also contain a collection of types grouped as a :ref:`LogicalGroupings` e.g.

.. code-block:: yaml

    requires:
      or:
        apt: ufw
        snap: ufw
      systemd:
        ufw: active

This requires the ufw package be installed as a snap or apt package and the corresponding systemd service be in active state.

Note that if more than one item in a group has the same type, a list must used e.g.

.. code-block:: yaml

    requires:
      and:
        - systemd:
            ufw: active
        - systemd:
            ssh: active

The final result of a list is obtained by applying the AND operator to all results.

Lastly, each requirement type can have an accompanying list of operators to be
applied to the outcome of that type. Each item in the list is a tuple with at
least one item - the operator - along with an optional second item which is
the second argument to the operator execution. The input is the outut of the
previous operator. Operators can be any `python operator <https://docs.python.org/3/library/operator.html>`_.

For supported "requirement type" properties see :ref:`requirement types`
