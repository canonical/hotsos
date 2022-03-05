# Overview

hotsos is a framework for software-defined analysis. It provides a high-level language (see [README](defs/README.md)) for defining checks and analysis of hosts and some common applications including:

  * Openstack
  * Kubernetes
  * Ceph
  * OpenvSwitch
  * Juju
  * MAAS
  * Vault
  * and more

There are a number of output options and formats. The default output is a yaml summary containing information specific to each application (plugin) type including issues and known bugs detected. Hotsos can be run against a host or [sosreport](https://github.com/sosreport/sos).

The code has the following structure:

  * core library code
  * yaml-defined checks ([defs](defs/README.md))
  * plugin extension code
  * test code

## Usage

See --help for usage info.

## Examples

An example **full** (yaml) summary can be found [here](examples/hotsos-example-openstack.summary.yaml)

An example **short** (yaml) summary can be found [here](examples/hotsos-example-openstack.short.summary.yaml)

## Install

You can either run from source or install Ubuntu snap e.g.

sudo snap install hotsos --classic

See https://snapcraft.io/hotsos for more info on usage.
