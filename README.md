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

Each plugin has associated checks or "scenarios" that seek to identify issues
and known bugs. The output is a summary from each plugin including key runtime
information as well issues or bugs detected along with suggestions on how to
deal with them. This information can be useful as an aid for further manual
analysis.

The default summary format is yaml and a number of other options and formats are
provided.

Hotsos is run directly on a host or against a [sosreport](https://github.com/sosreport/sos).

The code has the following structure:

* core python library (includes plugins)
* checks/scenarios (see documentation at [defs](hotsos/defs/README.md))
* python plugin extensions
* tests

## Usage

Say for example that you are running an Openstack Cloud and one of your
hypervisor nodes that is also running part of a Ceph storage cluster
is experiencing a problem with network connectivity to workloads. Simply
run hotsos on the node or against a sosreport generated from that node e.g.

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
issues or bugs detected. By default hotsos will only look at the last 24 hours of logs.
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

HotSOS can be installed in the following ways:

### Daily build Debian package

NOTE: this is the recommended method.

```console
$ sudo add-apt-repository ppa:ubuntu-support-team/hotsos
$ sudo apt install hotsos
```


### pypi

NOTE: requires Python >= 3.8

```console
$ sudo apt install python3-pip
$ pip install hotsos
```

NOTE: when upgrading be sure to upgrade dependencies since pip will not do this by default.
      To forcibly upgrade all dependencies you can use:

```
pip install --upgrade hotsos --upgrade-strategy eager
```

### snap

You can install as a snap e.g.

```console
$ sudo apt install snapd
$ sudo snap install hotsos --classic
```

See <https://snapcraft.io/hotsos> for more info on usage.

NOTE: the snap only currently works properly on Ubuntu Focal.

### source

```console
$ git clone https://github.com/canonical/hotsos
$ pip install -r hotsos/requirements.txt
$ ./hotsos/scripts/hotsos
```
