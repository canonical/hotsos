#!/usr/bin/env bash

# Set up logging.
touch '/var/log/juju/machine-1.log'
chown syslog:adm '/var/log/juju/machine-1.log'
chmod 0640 '/var/log/juju/machine-1.log'
exec >> '/var/log/juju/machine-1.log'
exec 2>&1

# Run the script.
'/var/lib/juju/tools/machine-1/jujud' machine --data-dir '/var/lib/juju' --machine-id 1 --debug
