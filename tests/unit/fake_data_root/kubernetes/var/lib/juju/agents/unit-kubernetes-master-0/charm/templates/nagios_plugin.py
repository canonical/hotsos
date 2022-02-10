#!/usr/bin/env python3

# Copyright (C) 2019 Canonical Ltd.

import nagios_plugin3
import socket
from subprocess import check_output

snap_resources = ['kubectl', 'kube-apiserver', 'kube-controller-manager',
                  'kube-scheduler', 'cdk-addons', 'kube-proxy']


def check_snaps_installed():
    """Confirm the snaps are installed, raise an error if not"""
    for snap_name in snap_resources:
        cmd = ['snap', 'list', snap_name]
        try:
            check_output(cmd).decode('UTF-8')
        except Exception:
            msg = '{} snap is not installed'.format(snap_name)
            raise nagios_plugin3.CriticalError(msg)


def test_connection(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((host, int(port)))
        s.shutdown(socket.SHUT_RDWR)
    finally:
        s.close()


def verify_remote_connection_to_apiserver():
    try:
        test_connection(socket.gethostbyname(socket.gethostname()), 6443)
    except Exception:
        raise nagios_plugin3.CriticalError("Unable to reach "
                                           "API server on remote port")


def main():
    nagios_plugin3.try_check(check_snaps_installed)
    nagios_plugin3.try_check(verify_remote_connection_to_apiserver)
    print("OK - API server is up and accessible")


if __name__ == "__main__":
    main()
