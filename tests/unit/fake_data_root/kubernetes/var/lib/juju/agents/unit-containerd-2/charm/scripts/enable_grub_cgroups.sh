#!/bin/bash

# Edits the grub defaults file to append the GRUB_CMDLINE_LINUX options and executes a
#  `juju-reboot` to reboot the machine.

status-set maintenance "Configuring and updating grub"

sed -i  's/GRUB_CMDLINE_LINUX=\"\"/GRUB_CMDLINE_LINUX=\"cgroup_enable=memory swapaccount=1\"/' /etc/default/grub
update-grub
status-set maintenance "Rebooting the machine"

juju-reboot
