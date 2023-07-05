Checks
------

A dictionary of labelled checks each of which is a grouping of properties (see
Supported Properties). Eack check is executed independently and produces a
boolean *result* of True or False.

Checks are normally implemented in conjunction with :ref:`Conclusions<conclusions>`
as part of :ref:`Scenarios<scenarios overview>`.

format:

.. code-block:: yaml

    checks:
      check1:
        <property1>
        <property2>
      check2:
        <property3>
        <property4>
      ...

    CACHE_KEYS
      search
      requires

usage:

.. code-block:: python

    <checkname>.result

Settings
^^^^^^^^

  * :ref:`Search<search>`
  * :ref:`Requires<requires>`
  * :ref:`Input<input>`


Conclusions
-----------

This indicates that everything beneath is a set of one or more conclusions to
be used by `Scenarios<scenarios overview>`. The contents of
this override are defined as a dictionary of conclusions labelled with
meaningful names.

A conclusion is defined as a function on the outcome of a set of checks along
with the consequent behaviour should the conclusion match. This is defined as
an issue type and message that will be raised. If multiple conclusions are
defined, they are given a :ref:`Priority<priority>` such that the highest one to
match is the one that is executed. See :ref:`Scenarios<scenarios overview>`
section for more info and examples.

The message can optionally use format fields which, if used, require
format-dict to be provided with key/value pairs. The values must be
an importable attribute, property or method.

format:

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

usage:

.. code-block:: python

    <conclusionname>.reached
    <conclusionname>.priority
    <conclusionname>.issue_message
    <conclusionname>.issue_type

Settings
^^^^^^^^

Decision
""""""""

This property is typically used in :ref:`Conclusions<conclusions>`.
CHECKS refers to a set of one or more :ref:`Checks<checks>` names organised as a
:ref:`LogicalCollection` to make a decision based on the outcome of more
checks.

format:

.. code-block:: yaml

    decision: CHECKS

usage:

.. code-block:: python

    <iter>

Priority
""""""""

Defines an integer priority. This is a very simple property that is typically
used by :ref:`conclusions` to associate a priority or precedence to
conclusions.

format:

.. code-block:: console

    priority:
      <int>

usage:

.. code-block:: python

    int(priority)

Raises
""""""

Defines an issue to raise along with the message displayed. For example a
:ref:`Checks<checks>` may want to raise an `issue_types <https://github.com/canonical/hotsos/blob/main/hotsos/core/issues/issue_types.py>`_
with a formatted message where format fields are filled using Python properties
or search results.

format:

.. code-block:: console

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
import path or a ``PROPERTY_CACHE_REF``:

.. code-block:: console

    PROPERTY_CACHE_REF
      A reference to a property cache item that takes one of two forms:

      '@<propertyname>.CACHE_KEY[:function]'
      '@checks.<checkname>.<propertyname>.CACHE_KEY[:function]'

      The latter is used if the property is within a "check" property.

    CACHE_KEY
      See individual property CACHE_KEYS for supported cache keys.

Both import paths and cache references can be suffixed with an optional
``:<function>`` where function is the name of a `python builtins <https://docs.python.org/3/library/functions.html>`_ function
or one of the following:

  * **comma_join** - takes a list or dict as input and returns ``', '.join(input)``
  * **unique_comma_join** - takes a list or dict as input and returns ``', '.join(set(input))``
  * **first** - takes a list as input and returns ``input[0]``

usage:

.. code-block:: python

    raises.type
    raises.message
    raises.format_dict

Requires
--------

Defines a set of one or more :ref:`requirements <requirement types>` to be executed with a pass/fail result.

If the result is based on the outcome of more than one requirement they must be grouped as a :ref:`LogicalCollection` (see **REQ_GROUP** below).
The final result is either True/False for *passes*.

NOTE: this property is implemented as a :ref:`mapped property <mappedproperties>` so the root *requires* name is optional.

format:

.. code-block:: console

    requires:
      REQ_DEFS

    REQ_DEFS
      This must be one (and only one) of the following:
        * single REQ_DEF
        * a REQ_GROUP
        * list containing a mix of REQ_GROUP/REQ_DEF

      The final result of a list is formed of AND applied to the
      individual results of each REQ_DEF or REQ_GROUP.

    REQ_DEF
      A single requirement (see Requirement Types).

    REQ_GROUP
      A LOGICAL_COLLECTION of one or more REQ_DEF e.g.

      and:
        - REQ_DEF1
        - REQ_DEF2
        - ...
      or:
        - REQ_DEF3
        - ...

    OPS_LIST
        List of tuples with the form (<operator>[,<arg2>]) i.e. each tuple has
        at least one item, the operator and an optional second item which is
        the second argument to the operator execution. The first argument is
        always the output of the REQ_DEF or previous operator.

        Operators can be any supported [python operator](https://docs.python.org/3/library/operator.html).

        If more than one tuple is defined, the output of the first is the input
        to the second.

Settings
^^^^^^^^

See :ref:`requirement types`
