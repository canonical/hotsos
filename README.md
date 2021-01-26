# hotsos

Tool to extract application-specific information from a [sosreport](https://github.com/sosreport/sos) which are commonly used as a source of debugging information.

When running hotsos you can choose from a selection of plugins and can run it against either a sosreport or live host.

There are multiple *verbosity* levels (`-v` flag) to choose from, each providing more fine-grained information from each plugin.

NOTE: hotsos is not intended to replace the functionality of [xsos](https://github.com/ryran/xsos) but rather to provide extra application-specific information to get a useful view of applications running on a host.

### Usage

- Get the list of plugins:
> hotsos --list-plugins

- Get details about *openstack*:
> hotsos /path/to/sos/report --openstack

- Get more details on *openstack*:
> hotsos /path/to/sos/report --openstack -v

- And even more details:
> hotsos /path/to/sos/report --openstack -vvv

## Install

You can either run from this repository directly or install Ubuntu snap e.g.

sudo snap install hotsos

See https://snapcraft.io/hotsos for more info on usage.
