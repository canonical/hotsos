#!/usr/bin/python3
OPENVSWITCH_SERVICES_EXPRS = [r"ovsdb-\S+",
                              r"ovs-vswitch\S+",
                              r"ovn\S+"]
OVS_PKGS_CORE = [r"openvswitch-switch",
                 r"ovn",
                 ]
OVS_PKGS_DEPS = [r"libc-bin",
                 ]
OVS_DAEMONS = {"ovs-vswitchd":
               {"logs": "var/log/openvswitch/ovs-vswitchd.log"},
               "ovsdb-server":
               {"logs": "var/log/openvswitch/ovsdb-server.log"}}
