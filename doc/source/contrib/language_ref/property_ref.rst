Defining Variables
==================

Using the ``vars`` property we can define one or more variables that can be referenced
from other properties. These are defined as a list of ``key: value`` pairs where
values can be standard types like str, int, bool e.g.

.. code-block:: yaml

  vars:
    sfoo: foo
    ifoo: 400
    bfoo: true

Alternatively a reference to a Python property can be provided. To do this you need to
prefix the import string with '@' e.g.

.. code-block:: yaml

  vars:
    foo: '@path.to.my.property'

If the property being imported belongs to a *factory* it must have the following form:

.. code-block:: yaml

  vars:
    foo: '@<modpath>.<factoryclassname>.<property>:<input>'

Variables are referenced/accessed from other properties by prefixing their name with a '$' e.g.

.. code-block:: yaml

  vars:
    foo: true
  checks:
    foo_is_true:
      requires:
        varops: [[$foo], [eq, true]]


Shared Property Settings
========================

These settings can be used by any property that chooses to implement them.

input
-----

Provides a common way to define input e.g. when doing a :ref:`search`. Supports a filesystem
path or `CLIHelper <https://github.com/canonical/hotsos/blob/main/hotsos/core/host_helpers/cli.py>`_
command. When a command is provided, its output is written to a temporary file
and *input.path* is set to the path of that file. The *path* and *command* settings are mutually exclusive.

This property is required by and used as input to the :ref:`search` property.

format:

.. code-block:: yaml

    input:
      command: hotsos.core.host_helpers.CLIHelper.<command>
      path: FS_PATH
      options: OPTIONS

or

.. code-block:: yaml

    input: FS_PATH

.. code-block:: console

    input: FS_PATH

    FS_PATH
      This is either a single or list of filesystem paths that must be
      relative to DATA_ROOT.

    OPTIONS
        disable-all-logs: True
          Used to disable --all-logs for the input. By default
          if --all-logs is provided to the hotsos client that will apply
          to *path* but there may be cases where this is not desired and
          this option supports disabling --all-logs.

        args: [arg1, ...]
          Used in combination with *command*. This is a list of args
          that will be provided to the command.

        kwargs: {kwarg1: val, ...}
          Used in combination with *command*. This is a dictionary
          of kwargs that will be provided to the command.

        args-callback: import.path.to.method
          Used in combination with *command*. This is the import path to
          a method that will be called and the return value must be a
          tuple of the form (<list>, <dict>) where the list is used as args
          to the command and dict is kwargs.

    CACHE_KEYS
      cmd_tmp_path

usage:

.. code-block:: python

    input.paths

search
------

Used to define search expression(s) and criteria. There are different types of
search expression that can be used depending on the data being searched and how
the results will be interpreted:

A "simple" search (`SearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_) involves a single pattern
and is used to match single lines.

A "sequence" search (`SequenceSearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_) to match
(non-overlapping) sequences.

A "passthrough sequence" is used for analysing overlapping sequences with
`LogEventStats <https://github.com/canonical/hotsos/tree/main/hotsos/core/analytics.py>`_. This requires a
callback method to be implemented to process the results and is designated using
the optional *passthrough-results* option. Search results are passed
to their handler as a raw `SearchResultsCollection <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_.

NOTE: this property is implemented as a :ref:`mapped property <mappedproperties>` so the *search* name is optional.

IMPORTANT: do not use global search properties. If you do this, the same search
tag will be used for all searches and it will not be possible to
distinguish results form more than one leaf node.

format:

.. code-block:: console

    search:
      expr|hint: <str> (simple search)
      start|body|end: (sequence search)
        expr: <str>
        hint: <str>
      passthrough-results: True|False (turns sequence search into passthrough)
      constraints: CONSTRAINTS

      NOTE: search expressions can be a string or list of strings.

    CONSTRAINTS:
      Optional constraints that can be used to filter search results. This
      is typically used in conjunction with [checks]([#checks]).

      search-result-age-hours: <int>
        Age from current date (CLIHelper.date()) that results must fall
        within. Default is infinite. This is used in conjunction with the
        expr property and requires the search pattern to contain a group at
        the start (index 1) to match a timestamp of the form
        YEAR-MONTH-DAY HOUR:MIN:SECS

      search-period-hours: <int>
        Period of time within which we expect to find results. Default is
        infinite. Like search-result-age-hours this also requires the search
        pattern to match a datetime at index 1.

      min-results: <int>
        Minimum number of search results required. If a search period is
        defined, these must occur within that period. Default is 1.

      min-hours-since-last-boot: <int>
        Search result must be at least this number of hours after the last
        boot time.

    CACHE_KEYS
      simple_search
      sequence_search
      sequence_passthrough_search

usage:

You can access each parameter individually:

.. code-block:: python

      search.expr
      search.hint

or when using keys start|body|end:

.. code-block:: python

      search.<key>.expr
      search.<key>.hint

Or you can access as a pre-prepared search type:

.. code-block:: python

      search.simple_search
      search.sequence_search
      search.sequence_passthrough_search

Once results have been obtained they can be filtered using which will
return a True/False value.

.. code-block:: python

      search.apply_constraints(searchtools.SearchResultsCollection)


requires
--------

Defines a set of requirements to be executed with a pass/fail result.

If the result is based on the outcome of more than one requirement they
must be grouped a :ref:`LogicalCollection` (see **REQ_GROUP** below). The
final results is either True/False for *passes*.

NOTE: this property is implemented as a :ref:`mapped property <mappedproperties>` so the *requires* name is optional.

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

usage:

.. code-block:: python

    requires.passes

Requirement Types
-----------------

These are the supported members of the :ref:`requires` (mapped) property. You can use any number or combination of these withing a requires definition, optionally using a
:ref:`LogicalCollection` for logical groupings.

path
^^^^

This has the same format as the input property and is used to
assert if a path exists or not. Note that all-logs is not applied
to the path.

format:

.. code-block:: console

    path: <path>

    CACHE_KEYS
      path_not_found
      paths


property
^^^^^^^^

Calls a Python property and if provided, applies a set of
operators. If no operators are specified, the "truth" operator
is applied to get a True/False result.

format:

.. code-block:: yaml

    property: <import path to python property>

or

.. code-block:: yaml

    property:
      path: <import path to python property>
      ops: OPS_LIST

.. code-block:: console

    CACHE_KEYS
      property
      ops
      value_actual

apt
^^^

Takes an apt package name or APT_INFO. Returns True if the package
exists and if APT_INFO provided, version is within ranges.

format:

.. code-block:: console

    apt: [package name|APT_INFO]

    APT_INFO
      single package name, list of packages or dictionary of
      <package name>: <version ranges> e.g.

      mypackage:
        - min: 0.0
          max: 1.0
        - min: 4.0
          max: 5.0

    CACHE_KEYS
      package
      version

snap
^^^^

Takes a snap package name or SNAP_INFO. Returns True if the package
exists and if SNAP_INFO provided, revision is within ranges.

format:

.. code-block:: console

    snap: [package name|SNAP_INFO]

    SNAP_INFO
      single package name, list of packages or dictionary of
      <package name>: <revision ranges> e.g.

      mypackage:
        - min: 0.0
          max: 1.0
        - min: 4.0
          max: 5.0

    CACHE_KEYS
      package
      revision

pebble
^^^^^^

Takes a pebble service and optionally some parameters to check.
Returns True if service exists and, if provided, parameters match.
Short and long forms are supported as follows.

format:

.. code-block:: yaml

    pebble: <service name>  (state not checked here)

or

.. code-block:: yaml

    pebble: [svc1, svc2 ...]  (state not checked here)

or

.. code-block:: yaml

    pebble: SVCS

    where SVCS is a dict of one or more services e.g.

    pebble:
      service_name:
        state: <service state>
        op: <python operator>  (optional. default is 'eq')
        processes: list of processes we expect to be running  (optional)
      ...

    CACHE_KEYS
      services

systemd
^^^^^^^

Takes a systemd service and optionally some parameters to check.
Returns True if service exists and, if provided, parameters match.
Short and long forms are supported as follows.

If a service name is provided using the started-after parameter,
the start time of that service (if it exists) must be at least
120s behind the primary service. The grace period is to avoid
false-positives on boot where many services are often started at
once.

format:

.. code-block:: yaml

    systemd: <service name>  (state not checked here)

or

.. code-block:: yaml

    systemd: [svc1, svc2 ...]  (state not checked here)

or

.. code-block:: yaml

    systemd: SVCS

    where SVCS is a dict of one or more services e.g

    systemd:
      service_name:
        state: <service state>
        op: <python operator>  (optional. default is 'eq')
        started-after: <other service name>  (optional)
        processes: list of processes we expect to be running  (optional)
      ...

    CACHE_KEYS
      services

config
^^^^^^

A dictionary containing the information required to perform some config checks.
Supports applying assertion rules to the contents of one or more config file.

format:

.. code-block:: console

    handler: <path>
      Import path to an implementation of core.host_helpers.SectionalConfigBase.

    path: <path>
      Optional path or list of paths used as input when creating config
      handlers. Each path must be a file or glob path (wildcard).

    assertions: ASSERTION
      One or more ASSERTION can be defined and optionally grouped using
      a LogicalCollection. The
      final result is either True/False for *passes*.

    ASSERTION
      key: name of setting we want to check.
      section: optional config file section name.
      value: expected value. Default is None.
      ops: OPS_LIST
      allow-unset: whether the config key may be unset. Default is False.

    CACHE_KEYS
      assertion_results - a string of concatenated assertion checks
      key - the last key to be checked
      ops - the last ops to be run
      value_actual - the actual value checked against

varops
^^^^^^

This provides a way to build an OPS_LIST using :ref:`vars <Defining Variables>` whereby the
first element must be a variable e.g.

format:

.. code-block:: console

    OPS_LIST where first element is a variable name (and all vars used are prefixed with $).

    CACHE_KEYS
      name: name of the variable used as input
      value: value of the variable used as input
      ops: str representation of ops list

example:

.. code-block:: yaml

    vars:
      myvar: 10
      limit: 5
    checks:
      checkmyvar:
        varops: [[$myvar], [gt, $limit], [lt, 100]]
    conclusions:
      ...


Main Properties
===============

checks
------

A dictionary of labelled checks each of which is a grouping of properties (see
Supported Properties). Eack check is executed independently and produces a
boolean *result* of True or False.

Checks are normally implemented in conjunction with :ref:`conclusions`
as part of :ref:`scenarios`.

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

  * :ref:`search`
  * :ref:`requires`
  * :ref:`input`


conclusions
-----------

This indicates that everything beneath is a set of one or more conclusions to
be used by `scenarios <../hotsos/core/ycheck/scenarios.py>`_. The contents of
this override are defined as a dictionary of conclusions labelled with
meaningful names.

A conclusion is defined as a function on the outcome of a set of checks along
with the consequent behaviour should the conclusion match. This is defined as
an issue type and message that will be raised. If multiple conclusions are
defined, they are given a :ref:`priority` such that the highest one to
match is the one that is executed. See :ref:`scenarios` section for more
info and examples.

The message can optionally use format fields which, if used, require
format-dict to be provided with required key/value pairs. The values must be
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

decision
""""""""

This property is typically used in :ref:`conclusions`.
CHECKS refers to a set of one or more :ref:`checks` names organised as a
:ref:`LogicalCollection` to make decision on the outcome of more
checks.

format:

.. code-block:: yaml

    decision: CHECKS

usage:

.. code-block:: python

    <iter>

priority
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

raises
""""""

Defines an issue to raise along with the message displayed. For example a
:ref:`checks` may want to raise an `issue_types <../hotsos/core/issues/issue_types.py>`_
with a formatted message where format fields are filled using Python properties
or search results.

format:

.. code-block:: console

    raises:
      type: <type>
      bug-id: <str>
      message: <str>
      format-dict: <dict>

If *type* is a `bug type <../hotsos/core/issues/issue_types.py>`_ then a *bug-id*
must be provided.

If the *message* string contains format fields these can be filled
using ```format-dict``` - a dictionary of key/value pairs where *key* matches a
format field in the message string and *value* is either a Python property
import path or a ``PROPERTY_CACHE_REF``::

        PROPERTY_CACHE_REF
          A reference to a property cache item that takes one of two forms:

          '@<propertyname>.CACHE_KEY[:function]'
          '@checks.<checkname>.<propertyname>.CACHE_KEY[:function]'

          The latter is used if the property is within a "check" property.

        CACHE_KEY
          See individual property CACHE_KEYS for supported cache keys.

Both import paths and cache references can be suffixed with an optional
``:<function>`` where function is the name of a  `python builtins <https://docs.python.org/3/library/functions.html>`_ function
or one of the following:

  * **comma_join** - takes a list or dict as input and returns ``', '.join(input)``
  * **unique_comma_join** - takes a list or dict as input and returns ``', '.join(set(input))``
  * **first** - takes a list as input and returns ``input[0]``

usage:

.. code-block:: python

    raises.type
    raises.message
    raises.format_dict

