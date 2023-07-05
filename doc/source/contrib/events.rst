Events Overview
===============

These checks are not currently run automatically and do require custom
callbacks to be implemented in plugin code to process results. Event
definitions can be found `here <https://github.com/canonical/hotsos/tree/main/hotsos/defs/events>`_.

Events should be used sparingly and the recommendation is to use :ref:`Scenarios<scenarios overview>`.

An event can be single or multi-line and the data source is defined with an
:ref:`Input<input>` property. All event checks must have an eponymous callback
method defined in the plugin that handles them.

To define an event first create a file with the name of the check(s) you
want to perform under the directory of the plugin you are using to handle the
event callback.

Supported Properties
  * :ref:`Input<input>`
  * :ref:`Search<search>`

Event Callbacks
===============
Events are coupled with a callback function that is called if the event has
matches and takes search results as input.

Event callbacks will typically use `EventProcessingUtils <https://github.com/canonical/hotsos/blob/main/hotsos/core/ycheck/events.py>`_
to categorise data for display in the summary. Search patterns using this
method must have at least one result group defined and can optionally have more.
Groups are used as follows; if a single group is used it must match the date
and the events will be tallied by date e.g.

.. code-block:: yaml

    2023-01-01: 10
    2023-01-02: 23
    2023-01-03: 4

The other way is to have three groups such that group 1 is date, group 2 is time
and group 3 matches a value this can be used as the root key for a tally e.g.

.. code-block:: yaml

    val1:
      2023-01-01: 10
      2023-01-02: 23
      2023-01-03: 4
    val2:
      2023-01-01: 3
      2023-01-02: 4
      2023-01-03: 10

See the class docstring for more information on how to use it.

Examples
========

Two types of searches are available here; single or multi line. A multi-line
search can be used in two ways; the first use is simply to have a "start" and
"end" expression and the results will have -start and -end appended to their
tags accordingly and the second use is to define a sequence which requires at
least a "start" and "body" with optional "end". Sequences are processed using
searchtools.SequenceSearchDef and all other searches use
searchtools.SearchDef. Single line search is defined using the "expr" key.

A single-line search on a file:

.. code-block:: yaml

    myeventname:
      input:
        path: path/to/my/file
      expr: <re.match pattern>
      hint: optional <re.match pattern> used as a low-cost filter

A multi-line search on a file:

.. code-block:: yaml

    myeventname:
      input:
        path: path/to/my/file
      start:
        expr: <re.match pattern>
      end:
        expr: <re.match pattern>

A sequence search on a file:

.. code-block:: yaml

    myeventname:
      input:
        path: path/to/my/file
      start:
        expr: <re.match pattern>
      body:
        expr: <re.match pattern>
      end:
        expr: <re.match pattern>
