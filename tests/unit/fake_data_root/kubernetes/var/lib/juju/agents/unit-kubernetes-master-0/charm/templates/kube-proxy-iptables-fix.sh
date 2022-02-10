#!/bin/sh

# add the chain, note that adding twice is ok as it will just error.
/sbin/iptables -t nat -N KUBE-MARK-DROP

# need to check the creation of the rule to ensure we only create it once.
if ! /sbin/iptables -t nat -C KUBE-MARK-DROP -j MARK --set-xmark 0x8000/0x8000 &> /dev/null; then
  /sbin/iptables -t nat -A KUBE-MARK-DROP -j MARK --set-xmark 0x8000/0x8000
fi
