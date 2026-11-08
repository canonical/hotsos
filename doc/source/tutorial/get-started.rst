Get started with hotsos
=======================

In this tutorial you will install hotsos, run it against a machine, and explore
the summary it produces. You will need a terminal on an Ubuntu machine (or a
`sosreport <https://github.com/sosreport/sos>`_ to analyse).

Install the tool
----------------

The quickest way to try hotsos is to install it from `PyPI
<https://pypi.org/project/hotsos/>`__ with pipx (which installs into an isolated
virtual environment and requires Python >= 3.8):

.. code-block:: bash

    sudo apt install pipx
    pipx install hotsos

For other installation methods, see :doc:`../how-to/install`.

Run your first analysis
-----------------------

hotsos runs all of its plugins by default. Each plugin inspects an application
or subsystem, runs its associated checks, and contributes a section to the
summary. Live-host analysis requires root privileges to read restricted
resources; sosreport analysis does not. Run hotsos against the local machine
and save the results:

.. code-block:: bash

    ubuntu@node1$ sudo hotsos --save
    INFO: analysing localhost /
    INFO: output saved to hotsos-output-1673868979
    INFO: available output formats:
    - yaml
    - json
    - markdown
    - html (click to view dashboard)

hotsos has now created a directory named ``hotsos-output-<id>`` containing the
same summary in several formats (YAML, JSON, MarkDown and HTML).

.. note::

   By default hotsos analyses the last 24 hours of logs. Use ``--all-logs`` to
   widen this to 7 days, and ``--max-logrotate-depth <days>`` to tune it
   further.

Read the summary
----------------

Default YAML output
^^^^^^^^^^^^^^^^^^^

By default the output is printed to standard out in YAML format and can be
viewed directly or with `yq <https://snapcraft.io/yq>`_ (install
with ``snap install yq``):

.. code-block:: bash

    ubuntu@node1$ yq . hotsos-output-1673868979/node1.summary.yaml
    version: 5.4.0-97-generic
    boot: ro
    cpu:
      vendor: genuineintel
      model: intel core processor (skylake, ibrs)
      smt: disabled
      cpufreq-scaling-governor: unknown
    potential-issues:
      MemoryWarnings:
        - 1 reports of oom-killer invoked in kern.log - please check. (origin=kernel.auto_scenario_check)

Each top-level key corresponds to a plugin. The ``potential-issues`` section is
where hotsos surfaces the problems and known bugs it detected, along with
suggested actions.

HTML dashboard
^^^^^^^^^^^^^^

When using the *--save* option the output is saved in multiple formats one of which is an
HTML dashboard that some might prefer to raw YAML or JSON.

Query a specific plugin
-----------------------

The JSON format is convenient for targeted queries with
`jq <https://stedolan.github.io/jq/>`_ (install with ``snap install jq``). For
example, to inspect only the storage plugin's findings:

.. code-block:: bash

    ubuntu@node1$ jq -r '.storage."potential-issues"' hotsos-output-1673868979/node1.summary.json
    {
      "BcacheWarnings": [
        "One or more of the following bcache bdev config assertions failed ... (origin=storage.auto_scenario_check)"
      ]
    }

Next steps
----------

You have installed hotsos, produced a summary and queried it. To go further:

* Browse example outputs for every plugin
  `on GitHub <https://github.com/canonical/hotsos/tree/main/examples>`_.
* Learn the day-to-day workflow in :doc:`../how-to/run-an-analysis`.
* Understand how the analysis is structured in
  :doc:`../explanation/architecture`.
* Write your own analysis by following :doc:`../how-to/write-checks`.
