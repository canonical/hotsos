Internals
=========

Scenarios and Events are written in YAML using a language described here and
implemented using the `propertree <https://github.com/dosaboy/propertree>`_
library.

Data Root
---------

The *data root* is a path referring to the root of the filesystem under analysis.
When analysing a host this defaults to '/' and when analysing a sosreport the
data root will point to the root of the unpacked sosreport.

Hotsos has runtime `configuration <https://github.com/canonical/hotsos/blob/main/hotsos/core/config.py>`_
that is global to all plugins and the `data_root` config must be set to this
path from the start. It is crucial that all paths used in hotsos are
relative to this path.

Property Overrides
------------------

Property overrides are blocks of yaml that map to Python objects using
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
        └── somemorechecks

Here *mychecks* and *somemorechecks* are directories and *mychecks.yaml* defines
overrides that apply to everything under *mychecks* such that any properties
defined in *mychecks.yaml* will be available in *checkthis.yaml*,
*checkthat.yaml* and any definitions under *somemorechecks* (but not
*altchecks*).

MappedProperties
----------------

Some properties use the `propertree <https://github.com/dosaboy/propertree>`_
mapped properties feature where they are implemented as a principal property with
one or more "member" properties. This allows us to write complex properties and
also has the benefit of supporting *shortform* definitions.

In the following example we have a property *mainprop* with two members *mp1*
and *mp2* that is written using the long format:

.. code-block:: yaml

    mycheck:
      mainprop:
        mp1:
          ...
        mp2:
          ...

And its shortform equivalent with principle name omitted looks like:

.. code-block:: yaml

    mycheck:
      mp1:
        ...
      mp2:
        ...

Both formats will be resolved and accessed in the same way i.e. in your code
you would do:

.. code-block:: python

    value1 = mycheck.mainprop.mp1
    value2 = mycheck.mainprop.mp2

Context
-------

Every property inherits context that is shared with all properties in the scope
of a file. This provides a way to share information across them such as
variable definitions.


PropertyCache
-------------

Every property (object) has a cache that it can use to store state.
This is useful to both avoid unnecessary re-execution and provide a means for
property objects to share state by "referencing" each others' cache. An example
of this is when formatting a message as part of a :ref:`raised issue <raises>`.
See the "Cache keys" section of a property description for supported keys.

As an example here is a :ref:`check<checks>` that compares the status of a systemd
service  and a :ref:`conclusion<conclusions>` that :ref:`raises<raises>` an
issue that references the check cache to format it's message:

.. code-block:: yaml

  checks:
    ufw_not_active:
      systemd:
        service: ufw
        state: active
        op: not
  conclusions:
    is_not_active:
      decision: ufw_not_active
      raises:
        type: SystemWarning
        message: '{name} is not active - panic!'
        format-dict:
          name: '@checks.ufw_not_active.requires.services:comma_join'

The format of a cache reference is as follows:

.. code-block:: console

    @checks.<checkname>.<propertyname>.<key>:<function>

Where *checkname* refers to the name of a check defined in the :ref:`checks<checks>`
section, *propertyname* refers to the name of a property defined within that
check and *key* must be one of those described in the "Cache keys" section of
the property. The *function* at the end is optional and applied to the value
retrieved. Supported functions are:

* comma_join - takes a list or dict as input and returns ', '.join(input)
* unique_comma_join - takes a list or dict as input and returns ', '.join(set(input))
* first - takes a list as input and returns input[0]

LogicalGroupings
----------------

The `propertree <https://github.com/dosaboy/propertree>`_ library has native
support for using logical operators both to group properties as well as
grouping property contents. This provides a way for properties to make a
decision based on a group of items where the group may be a single item,
list of items, one or more groups or a list of groups of items organised by
logical operator that will be used to determine their collective result. For
example:

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

Any property type that returns a boolean value can be used (e.g.
:ref:`requires` types). The final result is always AND applied to all
subresults.

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
This allows us to define a property for import in :ref:`vars <vars>` as follows:

.. code-block:: yaml

  vars:
    myval: '@mymod.myfactoryclass.attr:input'

One benefit of this being that *input* can be a string containing any
characters incl. ones that would not be valid in a property name.
