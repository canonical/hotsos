These are the supported members of the :ref:`requires` (mapped) property. You can use any number or combination of these within a requires definition, optionally using a
:ref:`LogicalGroupings` for logical groupings.

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

Another example:

.. code-block:: yaml

    apt:
      mypackage:
        - gt: 1.0
          lt: 3.0
        - eq: 5.0.3

In the above example *mypackage* must have a version between 1.0 and 3.0
(non-inclusive), or specifically 5.0.3.

Supported operators:

  * eq - equality comparison
  * lt - less than (<)
  * gt - greater than (>)
  * le/max - less than or equal (<=)
  * ge/min - greater than or equal (>=)

Cache keys:

  * package - name of each installed package
  * version - version of each installed package

Binary
---

Takes a binary name and optional list of version ranges. Returns True if
the binary exists and if provided, version is within ranges.

Usage:

.. code-block:: yaml

    binary:
      name: mybin
      handler: path.to.handler

Or with version ranges as follows:

.. code-block:: yaml

    binary:
      handler: path.to.bininterfacehandler
      mybin:
        - min: 0.0
          max: 1.0
        - min: 4.0
          max: 5.0

NOTE: the version checking logic is currently the same as for the :ref:`Apt` type.

Cache keys:

  * binary - name of each installed binary
  * version - version of each installed binary

Snap
----

Takes a snap package name and optional list of revision, version and channel.
The check returns True if the package is installed and at least one of the r/v/c
combination evaluates to True.

Usage:

.. code-block:: yaml

    snap: mypackage

Or with optional conditions as follows:

.. code-block:: yaml

    snap:
      mypackage:
        - revision:
            min: 1234
            max: 2345
          channel: 2.0/stable
        - version:
            eq: 1.17
        - channel: 3.0/beta

In the above example in order for snap requirement to be True, *mypackage* snap must be
installed in the system and either one of the following conditions must be true:

 * revision number is between *1234*-*2345* and the channel name is *2.0/stable*
 * version number is *1.17*
 * channel name is "3.0/beta"

Cache keys:

  * channel - channel of each installed package
  * package - name of each installed package
  * revision - revision of each installed package
  * version - version of each installed package

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
:ref:`LogicalGroupings` with AND as the default grouping. The final result
evaluates to True/False. Makes use of config "handlers" i.e. implementations of
*core.host_helpers.config.IniConfigBase* that support querying the
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


Expression
----------

Expressions allow the user to express a requirement in a human-readable domain specific language. Its purpose
is to provide a simplified, clear and concise expression grammar for all requirement types, and to eliminate
redundancies.

Usage:

.. code-block:: yaml

  checks:
    checkmyvar:
      # Explicit expression
      expression: |
        NOT 'test' IN @hotsos.core.plugins.plugin.class.property AND
        (@hotsos.core.plugins.plugin2.class.property_1 >= 500 OR
        @hotsos.core.plugins.plugin3.class.property_2)

Explicit expression form can be combined with other requirement types:

.. code-block:: yaml

  checks:
    checkmyvar:
      # Explicit expression
      expression: |
        # 'test' should not be present
        NOT 'test' IN @hotsos.core.plugins.plugin.class.property AND
        # Property value should exceed the threshold
        (@hotsos.core.plugins.plugin2.class.property_1 >= 500 OR
        # Property is True
        @hotsos.core.plugins.plugin3.class.property_2)
      systemd: test-service

Expressions can be declared implicitly when assigned as a literal to a check:

.. code-block:: yaml

  checks:
    # Implicit expression
    checkmyvar: |
        NOT 'test' IN @hotsos.core.plugins.plugin.class.property AND
        (@hotsos.core.plugins.plugin2.class.property_1 >= 500 OR
        @hotsos.core.plugins.plugin3.class.property_2)

Expression grammar consist of the following constructs to allow user to express a requirement:

Keywords
********

Keywords consist of a special set of words that has a purpose in the grammar. The current keywords are
[:ref:`None keyword` | :ref:`True keyword` | :ref:`False keyword`]

None keyword
==============

Case-insensitive. Equal to Python `None`.

**Examples**

.. code-block:: yaml

  expression: |
    NONE
    NoNE

True keyword
==============

Case-insensitive. Equal to Python `True`.

**Examples**

.. code-block:: yaml

  expression: |
    True
    TrUe

False keyword
===============

Case-insensitive. Equal to Python `False`.

**Examples**

.. code-block:: yaml

  expression: |
    FALSE
    False

Constants
*********

Constants are invariable values in the grammar. The current constants are [:ref:`float constant` | :ref:`integer constant` | :ref:`String literal`]

float constant
================

Floating point constants. `[0-9]+\.[0-9]+`

**Examples**

.. code-block:: yaml

  expression: |
    12.34
    -56.78

integer constant
==================

Integer constants. `[0-9]+`

**Examples**

.. code-block:: yaml

  expression: |
    1234
    -4567

String literal
==============

String literal. Declared with single quotes `''`

**Examples**

.. code-block:: yaml

  expression: |
    'this is a string literal'
    'this is @nother 1'
    '1234'
    '1.2'
    'True'

Functions
*********

Functions are defined as CaselessKeyword, followed by a `(` args `)`.

`caseless_keyword(expr1, ... exprN)`.

len(expr...)
============

Function to retrieve length of an expression. The expression argument should evaluate
to a construct that has a `length` property.

**Examples**

.. code-block:: yaml

  expression: |
    len('literal') # would return 7
    len('lit' + 'eral') # would return 7
    len(@class.property) # would return the length of the property value

not(expr...)
============

Function to negate an expression's boolean vlaue. The expression argument should evaluate
to a construct that is `boolable`.

**Examples**

.. code-block:: yaml

  expression: |
    not(True) # would return False
    not(None) # would return True
    not(3 == 4) # Would return True

file('path-to-file', 'property-name[optional]')
===============================================

Function to retrieve a file's properties. Returns True or False when called with one argument depending
whether the file exists or not. Returns the property's value when called with two arguments. Property names
are all the properties that `hotsos.core.host_helpers.filestat.FileObj` has.

** Examples **

.. code-block:: yaml

  expression: |
    # Returns True or False, depending on whether the `/path/to/file` exists or not.
    file('/path/to/file')

.. code-block:: yaml

  expression: |
    # Returns file's mtime property when file exists, YExprNotFound when the
    # file is absent. Raises an exception when the given property name is not
    # present on the service object.
    file('/path/to/file', 'mtime')

systemd('service-name', 'property-name[optional]')
==================================================

Function to retrieve a systemd service's properties. Returns True or False when called with one argument depending
whether the service exists or not. Returns the property's value when called with two arguments.

Property names are all the properties that `hotsos.core.host_helpers.systemd.SystemdService` has.

**Examples**

.. code-block:: yaml

  expression: |
    # Returns True or False, depending on whether the `systemd-resolve` service
    # exists or not.
    systemd('systemd-resolved')

.. code-block:: yaml

  expression: |
    # Returns the service's `start_time_secs` property value when the service file
    # exists, YExprNotFound when the service is absent. Raises an exception when the
    # given property name is not present on the service object.
    systemd('systemd-resolved', 'start_time_secs')

read_ini('path-to-ini', 'key', 'section[optional]', 'default[optional]')
========================================================================

Function to read values from an ini file. Returns the first matching key's value when called with two arguments. Returns
the key's value in the specific section when called with three arguments. Returns the value specified in `default` when
the `default` argument is provided and given key in given section is not found.

**Examples**

.. code-block:: yaml

  expression: |
    # would return the value of the first encountered key 'foo' from any section.
    # would return YExprNotFound when the key is not found.
    read_ini('/etc/ini-file', 'foo')

.. code-block:: yaml

  expression: |
    # would return the value of the key 'foo' from section 'bar.
    # would return YExprNotFound when the key is not found.
    read_ini('/etc/ini-file', 'foo', 'bar')

.. code-block:: yaml

  expression: |
    # would return the value of the key 'foo' from section 'bar'.
    # would return the string literal 'abcd' when the key is not found.
    read_ini('/etc/ini-file', 'foo', 'bar', 'abcd')

.. code-block:: yaml

  expression: |
    # would return the value of the key 'foo' from any section.
    # would return the string literal 'abcd' when the key is not found.
    read_ini('/etc/ini-file', 'foo', None, 'abcd')

read_cert('path-to-cert', 'property-name[optional]')
====================================================

Function to read values from a X509 certificate (e.g. a typical SSL certificate). Returns True or False depending whether
the certificate file 'path-to-cert' exist when called with a single argument. With two arguments, Returns the value of the
`property-name` when the certificate file `path-to-cert` exist, YExprNotFound otherwise.

Property names are all the properties that `hotsos.core.host_helpers.ssl.SSLCertificate` has.

**Examples**

.. code-block:: yaml

  expression: |
    # would return True or False depending on whether '/etc/ssl/cert' exist or not.
    read_cert('/etc/ssl/cert')

.. code-block:: yaml

    expression: |
      # Would return the certificate's expiry_date property when the certificate
      # file is present.
      # Raises an exception when property name cannot be found on SSLCertificate object.
      #read_cert('/etc/ssl/cert', 'expiry_date')

Runtime variables
*****************

Python property `@module.class.property_name`
=============================================

Retrieve the value of a runtime Python property. Raises an exception when a property with a given name is not found.

**Examples**

.. code-block:: yaml

  expression: |
    # would return the value of the property
    # Raises exception when property is absent.
    @hotsos.plugins.plugin.class_name.property_name


Operands
********

:ref:`Keywords` | :ref:`Constants` | :ref:`Functions` | :ref:`Runtime Variables`

Arithmetic operators
********************

plus sign (`+`)
===============

Indicate the sign of an Integer or Float.

**Examples**

.. code-block:: yaml

  expression: |
    # plus six
    +6
    # plus six
    +(+6)

minus sign (`-`)
================

Indicate the sign of an Integer or Float.

**Examples**

.. code-block:: yaml

  expression: |
    # plus six
    -(-6)
    # minus six
    -6

multiplication (`*`)
====================

Multiply the given operands for the operands that are multiplicable with each other.

**Examples**

.. code-block:: yaml

  expression: |
    # result is 0.6
    1 * 0.6

division(`/`)
=============

Perform a division with the given operands for the operands that supports division with each other.

**Examples**

.. code-block:: yaml

  expression: |
    # result is 2.5
    1 / 0.4

addition(`+`)
=============

Add two things with each other.

**Examples**

.. code-block:: yaml

  expression: |
    # result is 8
    3 + 5 # 8
    # result is 'aabb'
    'aa' + 'bb'

subtraction(`-`)
================

Subtract two things from each other.

**Examples**

.. code-block:: yaml

  expression: |
    # result is -9
    3 - 5 - 7

exponent (`\*\*`)
=================

Calculate the exponent of a number.

**Examples**

.. code-block:: yaml

  expression: |
    # result is 8
    2**3
    # result is 729
    9**3

Comparison operators
********************

Comparison operators allow users to compare values within expressions. These operators can be used to evaluate whether a particular condition is met.

less than (`<`, `LT`)
=====================

Evaluates whether the left operand is less than the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    3 < 5
    # result is False
    3.81 > 3.80

less than or equal (`<=`, `LE`)
===============================

Evaluates whether the left operand is less than or equal to the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    5 <= 5
    # result is False
    3.81 LE 3.80

greater than (`>`, `GT`)
========================

Evaluates whether the left operand is greater than the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is False
    3 > 5
    # result is True
    3.81 > (2.80 + 1)

greater than or equal (`>=`, `GE`)
==================================

Evaluates whether the left operand is greater than or equal to the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is False
    3 >= 5
    # result is True
    3.81 GE (3.80 + 0.01)

equal (`==`, `EQ`)
==================

Evaluates whether the left operand is equal to the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    3 == 3
    # result is False
    True == False
    # result is True
    'test' EQ 'test'

not equal (`!=`, `NE`, `<>`)
============================

Evaluates whether the left operand is not equal to the right operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    3 != 5
    # result is False
    3.81 <> (3.80 + 0.01)
    # result is True
    'test' NE None

in (`IN`)
=========

Evaluates whether the left operand is contained within the right operand (e.g., within a string or list).

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    'a' in 'ab'
    # result is True (assuming list of ints = [1,2,3])
    1 in @module.prop.list_of_ints

Logical operators
*****************

Logical operators allow users to combine multiple expressions. These operators evaluate the truthiness of expressions to determine the overall outcome.

logical and (`and`)
===================

Returns True if both operands are True.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    True and (5 < 3 or 'test' in 'testament')
    # result is False
    (3.3 <= 2) or (5 > 3 and 'rest' in 'testament')

logical or (`or`)
=================

Returns True if at least one of the operands is True.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    True or False
    # result is False
    False or not True

logical not (`not`)
===================

Returns the opposite boolean value of the operand.

**Examples**

.. code-block:: yaml

  expression: |
    # result is True
    not None
    # result is True
    not False

Comments
********

Comments are used to annotate the code and are ignored during execution. This can be useful for adding explanations or notes within the expression grammar.

Python-style comments (`#`)
===========================

Single-line comments that begin with `#`.

**Examples**

.. code-block:: yaml

  expression: |
    # This is a comment explaining what the expression does.
    not None


C-style comments (`//`, `/*...*/`)
==================================

Single-line comments using `//` or multi-line comments enclosed in `/*...*/`.

**Examples**

.. code-block:: yaml

  expression: |
  // This is a single-line comment

.. code-block:: yaml

  expression: |
  /* This is a
     multi-line comment */

Expression grammar
******************

- :ref:`Operands` | :ref:`Arithmetic operators` | :ref:`Comparison operators` | :ref:`Logical operators`

Note that comments are not the part of the expression and ignored by the parser.
