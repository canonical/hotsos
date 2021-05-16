#!/usr/bin/python3
OPENVSWITCH_SERVICES_EXPRS = [r"ovsdb-\S+",
                              r"ovs-vswitch\S+",
                              r"ovn\S+"]
OVS_PKGS = [r"libc-bin",
            r"openvswitch-switch",
            r"ovn",
            ]
OVS_DAEMONS = {"ovs-vswitchd":
               {"logs": "var/log/openvswitch/ovs-vswitchd.log"},
               "ovsdb-server":
               {"logs": "var/log/openvswitch/ovsdb-server.log"}}
