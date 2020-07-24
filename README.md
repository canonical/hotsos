# hotsos

This tool is intended to be used to extract information out of
sos reports that are commonly looked at when debugging problems.
It has a number of *plugins* that deal with extracting application
specific information.

It's designed to be able to run on both live systems as well as
sos reports.

It has multiple *verbosity* levels (`-v` flag) to get more fine-grained
information about one or more applications.

NOTE: hotsos is not intended to replace the functionality of
[xsos](https://github.com/ryran/xsos); rather this is directed towards extracting application specific
information that's not covered by xsos.

### Usage

- Get the list of plugins:
> hotsos --list-plugins

- Get details about *openstack*:
> hotsos /path/to/sos/report --openstack

- Get more details on *openstack*:
> hotsos /path/to/sos/report --openstack -v

- And even more details:
> hotsos /path/to/sos/report --openstack -vvv

