Defining
--------

Use the ``vars`` property to define one or more variables that can be referenced
from properties and settings. These are defined as a list of ``key: value`` pairs where
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

When *$foo* is used it will have the value of *myproperty*.

A :ref:`factory <FactoryClasses>` reference can also be defined using the following form:

.. code-block:: yaml

  vars:
    foo: '@<modpath>.<factoryclassname>.<property>:<input>'


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

Scope
-----

Variables are accessible from any property within the file in which they are defined. Global properties are not yet supported.
