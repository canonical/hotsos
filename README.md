# Overview

Hotsos is a framework for software-defined analysis. It provides a library of
plugins written in Python along with a [high-level
language](hotsos/defs/README.md) in which to implement checks and analysis and
report problems. Supported plugins include:

* Openstack
* Kubernetes
* Ceph
* Open vSwitch
* Juju
* MAAS
* Vault
* MySQL
* RabbitMQ
* and more

Each plugin has a set of associated checks or "scenarios" that run in the
context of that plugin and seek to identify issues. The output of running hotsos
is a summary produced by each plugin including key information about the runtime
of that application along with any issues detected. This summary also aims to
contain as much information needed to aid manual analysis beyond the automated
checks and is easily extensible.

The default summary format is yaml and a number of other options and formats are
provided.

Hotsos is either run directly against a host or a
[sosreport](https://github.com/sosreport/sos).

The code has the following structure:

* core library (includes plugins)
* yaml-defined checks (see documentation at [defs](hotsos/defs/README.md))
* plugin extensions e.g. summary output
* tests

## Usage

Let's say for example that you are running an Openstack Cloud and one of your
hypervisor nodes that also happens to be running part of a Ceph storage cluster
is experiencing a problem with network connectivity to workloads. You can simply
run hotsos either against a sosreport generated from that node or on that node
directly as follows:

```console
ubuntu@ncpu1$ hotsos -s
INFO: analysing localhost /
INFO: output saved to hotsos-output-1673868979
```

Now you will find a folder called `hotsos-output-1673868979` containing a
summary of information in a number of different formats. Taking the most common
yaml format we can see:

```console
ubuntu@ncpu1$ cat hotsos-output-1673868979/ncpu1.summary.yaml
```

This file will contain a per-plugin summary of information found along with any
issues detected. By default hotsos will only look at the last 24 hours of logs.
You can increase this with `--all-logs` which will by default give you 7 days
worth and if you want more you can use `--max-logrotate-depth <days>`.

Our folder also contains other formats of the same information and one of those
is json which can easily be queried using a tool called
[jq](https://stedolan.github.io/jq/). Using this useful tool we can easily query
for specific information e.g.

```console
ubuntu@ncpu1$ jq -r '.storage."potential-issues"' hotsos-output-1673868979/ncpu1.summary.json
{
  "BcacheWarnings": [
    "One or more of the following bcache bdev config assertions failed: sequential_cutoff eq \"0.0k\"/actual=\"4.0M\", cache_mode eq \"writethrough [writeback] writearound none\"/actual=\"writethrough [writeback] writearound none\", writeback_percent ge 10/actual=\"10\" (origin=storage.auto_scenario_check)",
    "One or more of the following bcache cacheset config assertions failed: congested_read_threshold_us eq 0/actual=\"2000\", congested_write_threshold_us eq 0/actual=\"20000\" (origin=storage.auto_scenario_check)"
  ]
}
```

## Examples

An example **full** (yaml) summary can be found
[here](examples/hotsos-example-openstack.summary.yaml)

An example **short** (yaml) summary can be found
[here](examples/hotsos-example-openstack.short.summary.yaml)

## Install

HotSOS is distributed using the following methods:

### pypi

You can install using Python pip e.g.

```console
$ sudo apt install python3-pip
$ pip install hotsos
```

NOTE: currently requires Python >= 3.8

### snap

You can install as a snap e.g.

```console
$ sudo apt install snapd
$ sudo snap install hotsos --classic
```

See <https://snapcraft.io/hotsos> for more info on usage.

or run from source e.g.

```console
$ git clone https://github.com/canonical/hotsos
$ pip install -r hotsos/requirements.txt
$ ./hotsos/scripts/hotsos
```
