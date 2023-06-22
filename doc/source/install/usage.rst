Using Hotsos
============

Hotsos supports a number of application/subsystem plugins. It will by default run all
plugins and each will in turn execute its associated checks and extensions.
Once complete, the output of each plugin is collected and output as a summary. This
output will contain key information about the associated plugin/subsystem as well as
the results of any analysis that identified issues or known bugs. For more information
on how analysis and extensions are implemented see the :doc:`Contributor Guide <../contrib/index>`.

Hotsos uses the concept of a "data root" which is somewhat analogous to a chroot in which it looks
for data e.g. filesystem or cli commands. The default root is '/' (i.e. local host) but you can
also provide a path to an already unpacked sosreport.

Let's say for example that you are running an Openstack Cloud and one of your
hypervisor nodes that is also running part of a Ceph storage cluster
is experiencing a problem with network connectivity to workloads. Simply
run hotsos on the node or against a sosreport generated from that node e.g.

.. code-block:: bash

    ubuntu@ncpu1$ hotsos --save
    INFO: analysing localhost /
    INFO: output saved to hotsos-output-1673868979

Now you will find a folder called `hotsos-output-1673868979` containing a
summary of information in a number of different formats. This summary contains
per-plugin information as described above. By default hotsos will look at the
last 24 hours of logs. You can increase this with `\-\-all-logs` which will by
default give you 7 days and that is adjustable with `\-\-max-logrotate-depth <days>`.

Taking the yaml format and using `yq <https://snapcraft.io/yq>`_ (install with `snap install yq`) to query it we get:

.. code-block:: bash

    ubuntu@ncpu1$ yq . hotsos-output-1673868979/ncpu1.summary.yaml
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

The output folder will also contain other formats of the same information and one of those
is json which can easily be queried using a tool called `jq <https://stedolan.github.io/jq/>`_ (install with `snap install jq`).
Using this useful tool we can easily query for specific information e.g.

.. code-block:: bash

    ubuntu@ncpu1$ jq -r '.storage."potential-issues"' hotsos-output-1673868979/ncpu1.summary.json
    {
      "BcacheWarnings": [
        "One or more of the following bcache bdev config assertions failed: sequential_cutoff eq \"0.0k\"/actual=\"4.0M\", cache_mode eq \"writethrough [writeback] writearound none\"/actual=\"writethrough [writeback] writearound none\", writeback_percent ge 10/actual=\"10\" (origin=storage.auto_scenario_check)",
        "One or more of the following bcache cacheset config assertions failed: congested_read_threshold_us eq 0/actual=\"2000\", congested_write_threshold_us eq 0/actual=\"20000\" (origin=storage.auto_scenario_check)"
      ]
    }

Examples
========

Some example outputs for each plugin can be found `here <https://github.com/canonical/hotsos/tree/main/examples>`_. The *\*.short.\** summary files were generated using the `\-\-short` option. Note that if using the `\-\-save` option, all formats are saved automatically so this option would have no effect.

