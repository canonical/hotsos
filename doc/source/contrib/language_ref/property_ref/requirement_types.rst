These are the supported members of the :ref:`requires` (mapped) property. You can use any number or combination of these withing a requires definition, optionally using a
:ref:`LogicalCollection` for logical groupings.

path
----

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
--------

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
---

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
----

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
------

Takes a pebble service and optionally some parameters to check.
Returns True if the service exists and, if provided, parameters match.
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
-------

Takes a systemd service and optionally some parameters to check.
Returns True if the service exists and, if provided, parameters match.
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
------

A dictionary containing the information required to perform some config checks.
Supports applying assertion rules to the contents of one or more config files.

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
------

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

