Internals
=========

Property Overrides
------------------

Property overrides are blocks of yaml that map to Python classes using
`propertree <https://github.com/dosaboy/propertree>`_.

Property Scope
--------------

Overrides abide by rules of inheritance. They are accessed at leaf nodes and can
be defined and overridden at any level. Since definitions can be organised using
files and directories, the latter requires a means for applying directory
globals. Similar to pre-requisites, this is done by defining overrides in a file
that shares the name of the directory e.g.

.. code-block:: console

    myplugin/
    ├── altchecks
    └── mychecks
        ├── checkthat.yaml
        ├── checkthis.yaml
        ├── mychecks.yaml
        └── someotherchecks

Here *mychecks* and *somemorechecks* are directories and *mychecks.yaml* defines
overrides that apply to everything under *mychecks* such that any properties
defined in *mychecks.yaml* will be available in *checkthis.yaml*,
*checkthat.yaml* and any definitions under *somemorechecks* (but not
*altchecks*).

MappedProperties
----------------

Some properties use the `propertree <https://github.com/dosaboy/propertree>`_
mapped properties feature where they are implemented as a principal property with
one or more "member" properties. This is needed to write complex properties and
also has the benefit of supporting *shortform* definitions. For example if we
have a property *mainprop* and it has two member properties *mp1* and *mp2* it
can be defined using the long format:

.. code-block:: yaml

    mycheck:
      mainprop:
        mp1:
          ...
        mp2:
          ...

or shortform i.e. where the principle name is omitted:

.. code-block:: yaml

    mycheck:
      mp1:
        ...
      mp2:
        ...

and both formats will be resolved and accessed in the same way i.e. in your code you would do:

.. code-block:: python

    value1 = myleaf.mainprop.mp1
    value2 = myleaf.mainprop.mp2

Context
-------

Every property object inherits a context object that is shared across all
properties, providing a way to share information across them.

Caching
-------

Every property class has a cache that it can use to store state. This is useful
both within a property class e.g. to avoid re-execution of properties and
between properties e.g. if one property wishes to reference a value within
another property (see :ref:`raises`). Not all properties make use of their
cache but those that do will expose cached fields under a **CACHE_KEYS**
section.

LogicalCollection
-----------------

This provides a way for properties to make a decision based on a tree of items
where the items may be a single item, list of items, one or more groups or a
list of groups of items organised by logical operator that will be used to
determine their collective result. For example:

.. code-block:: yaml

    and: [C1, C2]
    or: [C3, C4]
    not: C5
    nor: [C1, C5]

This would be the same as doing::

    (C1 and C2) and (C3 or C4) and (not C5) and not (C1 or C5)

And this can be implemented as a list of dictionaries for a more complex
operation e.g.

.. code-block:: yaml

    - and: [C1, C2]
      or: [C3, C4]
    - not: C5
      and: C6

Which is equivalent to::

    ((C1 and C2) and (C3 or C4)) and ((not C5) and C6)

Any property type can be used and which ones are used will
depend on the property implementing the collection. The final result is
always AND applied to all subresults.

FactoryClasses
--------------

Hotsos has support for factory classes. These classes can dynamically
generate objects using an input provided as an attribute (setattr). Properties
of these new objects can be called (getattr) as follows:

.. code-block:: python

    from mymod import myfactoryclass
    obj = myfactoryclass().input
    val = obj.attr

This creates a new object using *input* as input and then *attr* is called on that object.
This allows us to define a property for import in :ref:`vars <defining variables>` as follows:

.. code-block:: yaml

  vars:
    myval: '@mymod.myfactoryclass.attr:input'

One benefit of this being that *input* can be a string containing any
characters incl. ones that would not be valid in a property name.
