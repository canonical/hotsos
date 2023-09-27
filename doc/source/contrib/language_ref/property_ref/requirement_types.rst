These are the supported members of the :ref:`requires` (mapped) property. You can use any number or combination of these within a requires definition, optionally using a
:ref:`LogicalCollection` for logical groupings.

Path
----

This has the same format as the input property and is used to
assert if a path exists or not. Note that all-logs is not applied
to the path.

Usage:

.. code-block:: yaml

    path: <path>

Cache keys:

  * path_not_found - list of paths that were provided but do not exist.
  * paths - list of paths provided.


Property
--------

Imports a Python property and applies one or more operators to its value to get
a boolean True/False result. By default the "truth" operator is applied.

Usage:

.. code-block:: yaml

    property: <import path to python property>

or

.. code-block:: yaml

    property:
      path: <import path to python property>
      ops: OPS_LIST

Cache keys:

  * ops - list of operators applied to property value
  * property - import path
  * value_actual - value of property

Apt
---

Takes an apt package name and optional list of version ranges. Returns True if
the package exists and if provided, version is within ranges.

Usage:

.. code-block:: yaml

    apt: mypackage

Or with version ranges as follows:

.. code-block:: yaml

    apt:
      mypackage:
        - min: 0.0
          max: 1.0
        - min: 4.0
          max: 5.0

In the above example *mypackage* must have a version between 0.0 and 1.0 or
4.0 and 5.0 inclusive.

Cache keys:

  * package - name of each installed package
  * version - version of each installed package

Snap
----

Takes a snap package name and optional list of revision ranges. Returns True if
the package exists and if provided, revision is within ranges.

Usage:

.. code-block:: yaml

    snap: mypackage

Or with revision ranges as follows:

.. code-block:: yaml

    snap:
      mypackage:
        - min: 1234
          max: 2345
          channel: 2.0/stable
        - min: 3456
          max: 4567

In the above example *mypackage* must have a revision between *1234* and *2345*
or 3456 and 4567 inclusive. If *mypackage* revision is between *1234* and
*2345* it must also be from channel *2.0/stable*

Cache keys:

  * channel - channel of each installed package
  * package - name of each installed package
  * revision - revision of each installed package

Pebble
------

Takes a pebble service name and optional parameters to check.
Returns True if the service exists and, if provided, parameters match.
Short and long forms are supported as follows.

Usage:

.. code-block:: yaml

    pebble: <service name>  (state not checked here)

or

.. code-block:: yaml

    pebble: [svc1, svc2 ...]  (state not checked here)

or

.. code-block:: yaml

    pebble:
      service_name:
        state: <service state>
        op: <python operator>  (optional. default is 'eq')
        processes: list of processes we expect to be running  (optional)


Cache keys:

  * services - list of service names

Systemd
-------

Takes a systemd service name and optional parameters to check.
Returns True if the service exists and, if provided, parameters match.
Short and long forms are supported as follows.

If a service name is provided using the started-after parameter,
the start time of that service (if it exists) must be at least
120s behind the primary service. The grace period is to avoid
false-positives on boot where many services are often started at
once.

The following example shows the simplest form whereby only a service name is
provided. This returns *True* if the service exists but does not check state.

.. code-block:: yaml

    systemd: <service name>

A list of service names can also be provided. The first service found not to
exist causes it to return *False*.

.. code-block:: yaml

    systemd: [svc1, svc2 ...]  (state not checked here)

This next example shows a more thorough check:

.. code-block:: yaml

    systemd:
      service_name:
        op: eq
        processes: ['aproc']
        started-after: anotherservice
        state: active

Here we check that the service exists, has state == "active" (as per the *op*
field that can be any suitable `python operator <https://docs.python.org/3/library/operator.html>`_),
was started after service *anotherservice* and has a running process called "aproc".

NOTE: when using this form, at least one field must be set.

Cache keys:

* services - list of service names we have checked

Config
------

Perform config checks by applying assertion rules to the contents of config
file. Assertions are defined as a list that is grouped as a
:ref:`LogicalCollection` with AND as the default grouping. The final result
evaluates to True/False. Makes use of config "handlers" i.e. implementations of
*core.host_helpers.config.SectionalConfigBase* that support querying the
contents of config files in a common way.

Usage:

.. code-block:: yaml

    config:
      handler: <import path>
      path: <path to config file>
      assertions:
        - allow-unset: <bool>
          key: <str>
          ops: <list>
          section: <str>
          value: <str> or <bool>

The value of *key* can be checked by either providing a *value* to which it is
compared or by setting *ops* to a list of
`operations <https://docs.python.org/3/library/operator.html>`_. Only one of
*value* and *ops* should be used to check a value.

Optional parameter *allow-unset* (default=True) determines if *key* may be
unset or not found.

NOTE: *path* must be relative to the :ref:`data root <data root>`.

Example:

.. code-block:: yaml

    checks:
      checkcfg:
        config:
          handler: hotsos.core.plugins.openstack.OpenstackConfig
          path: etc/nova/nova.conf
          assertions:
            - key: debug
              ops: [[eq, true]]
              section: DEFAULT

Cache keys:

* assertion_results - string of concatenated assertion checks
* key - the last key to be checked
* ops - the last ops to be run
* value_actual - the value of the last key to be checked

Varops
------

This provides a way to define a list of operations to be executed in sequence.
Each operation is defined as a tuple of size one or two. The first operation acts
as the input and is defined as a singleton of one variable (see
:ref:`vars <vars>`). Successive operations take as input the output of the
previous operation and are defined as one or two tuple objects where the first
element is a python `operator <https://docs.python.org/3/library/operator.html>`_ and
the optional second element is an argument as required by the operator.

Usage:

.. code-block:: yaml

    vars:
      myvar: 10
      limit: 5
    checks:
      checkmyvar:
        varops: [[$myvar], [gt, $limit], [lt, 100]]

Cache keys:

* input_ref: name of the variable used as input
* input_value: value of the variable used as input
* ops: str representation of ops list

