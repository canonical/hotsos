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
search expressions that can be used depending on the data being searched and how
the results will be interpreted:

A "simple" search (`SearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_) involves a single pattern
and is used to match single lines.

A "sequence" search (`SequenceSearchDef <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_) is used to match
(non-overlapping) sequences.

A "passthrough sequence" is used for analysing overlapping sequences with
`LogEventStats <https://github.com/canonical/hotsos/tree/main/hotsos/core/analytics.py>`_. This requires a
callback method to be implemented to process the results and is designated using
the optional *passthrough-results* option. Search results are passed
to their handler as a raw `SearchResultsCollection <https://github.com/dosaboy/searchkit/tree/main/searchkit>`_.

NOTE: this property is implemented as a :ref:`mapped property <mappedproperties>` so the *search* name is optional.

IMPORTANT: do not use global search properties. If you do this, the same search
tag will be used for all searches and it will not be possible to
distinguish results from more than one leaf node.

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

