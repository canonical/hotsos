Scenarios Overview
==================

Scenarios provide a way to define analysis in terms of :ref:`Checks<checks>` and
:ref:`Conclusions <conclusions>` where the latter are derived from decisions based
on the outcome of one or more checks.

Scenarios run automatically and are written in YAML. See existing
definitions for examples. They are grouped by plugin at the top level
and groupings beneath are purely logical/organisational.

A scenario must define its own set of :ref:`Checks<checks>` and :ref:`Conclusions<conclusions>`
and while you can have more than one scenario per file, it is recommended
to keep one per file for readability and testability purposes.

Checks are evaluated independently of each other and the results are saved for
subsequent :ref:`Decision<decision>` when forming :ref:`Conclusions<conclusions>`. They are also only
evaluated when referenced from a :ref:`Decision<decision>` (basically lazy loaded).
Also, checks that are :ref:`logically grouped <LogicalCollection>` are evaluated
until the minimum number of items has
been evaluated to determine the outcome of that group.

For example if we have three checks C1, C2 and C3 where C1 is True and C2 is False,
the following would never evaluate C3 as it will not impact the final result:

.. code-block:: yaml

  decision:
    and:
      - C1
      - C2
      - C3

And in the following, only C1 would be evaluated (since it it True):

.. code-block:: yaml

  decision:
    or:
      - C1
      - C2
      - C3

Conclusions are defined as a decision based on the outcome of one or more
:ref:`Checks<checks>` along with information such as the issue and message to
raise if a conclusion is matched. Conclusions can be given
:ref:`Priority<priority>` so that one can be selected in the event of multiple
positives. This is helpful for defining fallback conclusions.

The following propeties are mandatory when writing a scenario:

  * :ref:`Checks<checks>`
  * :ref:`Conclusions<conclusions>`

See :ref:`language reference<Main Properties>` for details on how to configure these properties.

Example Scenario
================

Lets say for example that we have a systemd service called *neverfail* that
writes logs to file */var/log/neverfail.log*. We want to raise an issue if we
see that the log file has more than 10 occurrences of ERROR in the last hour.
To do this we can write the following scenario that contains two conclusions;
the first is given the highest priority i.e. supersedes others used if it
matches and the second is a fallback:

.. code-block:: yaml

    vars:
      mem_current: '@hotsos.core.host_helpers.systemd.ServiceFactory.memory_current:neverfail'
    checks:
      is_enabled:
        systemd:
          neverfail: enabled
      high_mem_usage:
        varops: [[$mem_current], [gt, 5368709120]]
      logs_over_limit:
        input: var/log/neverfail.log
        search:
          constraints:
            min-results: 10
            results-age-hours: 24
    conclusions:
      limit_reached_and_rx_drops:
        priorty: 2
        decision:
          - is_enabled
          - logs_over_limit
          - high_mem_usage
        raises:
          type: ServiceWarning
          message: >-
            neverfail service is reporting errors and has high memory usage.
      limit_reached_only:
        priorty: 1
        decision:
          - is_enabled
          - logs_over_limit
        raises:
          type: ServiceWarning
          message: >-
            neverfail service is reporting errors.

