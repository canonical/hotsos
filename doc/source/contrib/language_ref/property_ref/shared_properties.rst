NOTE: these properties can be used on their own or in conjunction with others e.g. :ref:`checks`.

Input
=====

Provides a common way to define input. Supports a filesystem
path or `command <https://github.com/canonical/hotsos/blob/main/hotsos/core/host_helpers/cli.py>`_.
When a command is provided, its output is written to a temporary file
and *input.path* is set to the path of that file.

This property is required by and used as input to the :ref:`search` property.

Usage:

.. code-block:: yaml

    input:
      command: hotsos.core.host_helpers.CLIHelper.<command>
      path: <path>
      options:
        disable-all-logs: <bool>
        args: [arg1]
        kwargs:
          key1: val1
        args-callback: import.path.to.method

The *path* and *command* settings are mutually exclusive. A *path* can be a
single or list of filesystem paths that must be relative to :ref:`Data Root`.

By default if --all-logs is provided to the hotsos client that will apply
to *path* but there may be cases where this is not desired and
*disable-all-logs* can be used to disable this behaviour for a specific path.

When input is the output of a command, the execution of that command may
itself require some input. Both *args* and *kwargs* can be set as a list and/or
dictionary respectively and will be providing as input to the
`CLIHelper command <https://github.com/canonical/hotsos/blob/main/hotsos/core/host_helpers/cli.py>`_.

Sometimes we may way to dynamically generate the input args to *command*. For
this purpose we can use *args-callback* which is set to the import path of
a method whose return value must be a  tuple of the form (<list>, <dict>) where
the list is used as args to the command and dict is kwargs.

Cache keys:
* cmd_tmp_path

Search
======

Used to define a search using expression(s) and constraints. Different types of
search expressions that can be used depending on the data being searched and how
the results will be interpreted:

**simple** search (`SearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_) - a single pattern
used to match single lines.

**sequence** search (`SequenceSearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_)  - used to match
(non-overlapping) sequences.

Search results are passed to their handler as a raw `SearchResultsCollection <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_.

This property is implemented as a :ref:`mapped property <mappedproperties>` so the *search* name is optional.

IMPORTANT: do not use global search properties. If you do this, the same search
tag will be used for all searches and it will not be possible to
distinguish results from more than one leaf node.

Usage:

.. code-block:: yaml

    search:
      # the following are used to define a "simple" search
      expr: <str>
      hint: <str>
      # the following are used to define a "sequence" search
      start: <str>
      body: <str>
      end: <str>
      # If this is set to True it enables a passthrough sequence
      passthrough-results: True|False
      constraints:
        # Epoch (to current date i.e. CLIHelper.date()) that
        # results must fall within. Default is infinite.
        search-result-age-hours: <int>
        # Period of time within which we expect to find results.
        # Default is infinite.
        search-period-hours: <int>
        # Minimum number of search results required. If a search
        # period is defined, these must occur within that period.
        # Default is 1.
        min-results: <int>
        # Search result must be at least this number of hours
        # after the last boot time.
        min-hours-since-last-boot: <int>

Search expressions can be defined as a single string or list of strings.

If you want to analyse logs that contain overlapping sequences, perhaps from
multiple threads running concurrently, a **passthrough sequence** search is
used by setting *passthrough-results* to True. This will leverage
`LogEventStats <https://github.com/canonical/hotsos/tree/main/hotsos/core/analytics.py>`_
and requires a callback method to be implemented to process the results.


Constraints are used to filter search results and are typically used in
conjunction with :ref:`checks`. In order to use constraints, search
expressions must match a timestamp using result group 1. The format of
timestamps e.g. in logs and command outputs will vary and there are handlers in
the code to support common formats.

Cache keys:

* simple_search - a *searchkit.SearchDef* object
* sequence_search - a *searchkit.SequenceSearchDef* object
* sequence_passthrough_search - a list of *searchkit.SearchDef* objects

The above keys are mostly used for internal purposes and the following extra
entries are added to provide a way to access search results in :ref:`raises`
(also see :ref:`PropertyCache`):

* search.results_group_<int> - extract the value from result group <int>
* search.num_results - the number of results found by this search

In the following example we demonstrate how to use these keys. A file called
*var/log/myapp.log* has contents:

.. code-block:: console

    2023-10-12 13:22:01 ERROR: queue 'small_queue' is full
    2023-10-12 14:12:33 ERROR: queue 'small_queue' is full

And we have a :ref:`scenario<scenarios overview>` like:

.. code-block:: yaml

    checks:
      errorsfound:
        input: var/log/myapp.log
        expr: '\S+ \S+ ERROR: queue ''(\S+)'' is full'
    conclusions:
      haserrors:
        decision: errorsfound
        raises:
          type: SomeWarning
          message: >-
            found {count} reports of queue full for queue(s): {queues}
          format-dict:
            count: '@checks.errorsfound.search.num_results'
            queues: '@checks.errorsfound.search.results_group_1:unique_comma_join'

The message string output would look like:

.. code-block:: console

    found 2 "queue full" error(s) for queue(s): small_queue

