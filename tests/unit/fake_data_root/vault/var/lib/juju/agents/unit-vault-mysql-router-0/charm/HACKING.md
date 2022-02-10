# Overview

This charm is developed as part of the OpenStack Charms project, and as such you
should refer to the [OpenStack Charm Development Guide](https://github.com/openstack/charm-guide) for details on how
to contribute to this charm.

You can find its source code here: <https://opendev.org/openstack/charm-mysql-router>

# To Do

## Actions

 Pause Resume
 Service stop/start


## Tech Debt

 * System User and Group

 * Service management
   * Can we have a non-systemd services?
   * Create a systemd shim?

 * Configuration updates
   * Post bootstrap config changes
   * Service Restarts
