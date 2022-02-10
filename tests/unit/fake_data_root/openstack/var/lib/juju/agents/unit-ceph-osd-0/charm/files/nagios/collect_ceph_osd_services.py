#!/usr/bin/env python3

# Copyright (C) 2018 Canonical
# All Rights Reserved
# Author: Alex Kavanagh <alex.kavanagh@canonical.com>

import os
import subprocess
from pwd import getpwnam

# fasteners only exists in Bionic, so this will fail on xenial and trusty
try:
    import fasteners
except ImportError:
    fasteners = None

SYSTEMD_SYSTEM = '/run/systemd/system'
LOCKFILE = '/var/lock/check-osds.lock'
CRON_CHECK_TMPFILE = 'ceph-osd-checks'
NAGIOS_HOME = '/var/lib/nagios'


def init_is_systemd():
    """Return True if the host system uses systemd, False otherwise."""
    if lsb_release()['DISTRIB_CODENAME'] == 'trusty':
        return False
    return os.path.isdir(SYSTEMD_SYSTEM)


def lsb_release():
    """Return /etc/lsb-release in a dict"""
    d = {}
    with open('/etc/lsb-release', 'r') as lsb:
        for el in lsb:
            k, v = el.split('=')
            d[k.strip()] = v.strip()
    return d


def get_osd_units():
    """Returns a list of strings, one for each unit that is live"""
    cmd = '/bin/cat /var/lib/ceph/osd/ceph-*/whoami'
    try:
        output = (subprocess
                  .check_output([cmd], shell=True).decode('utf-8')
                  .split('\n'))
        return [u for u in output if u]
    except subprocess.CalledProcessError:
        return []


def do_status():
    if init_is_systemd():
        cmd = "/usr/local/lib/nagios/plugins/check_systemd.py ceph-osd@{}"
    else:
        cmd = "/sbin/status ceph-osd id={}"

    lines = []

    for unit in get_osd_units():
        try:
            output = (subprocess
                      .check_output(cmd.format(unit).split(),
                                    stderr=subprocess.STDOUT)
                      .decode('utf-8'))
        except subprocess.CalledProcessError as e:
            output = ("Failed: check command raised: {}"
                      .format(e.output.decode('utf-8')))
        lines.append(output)

    _tmp_file = os.path.join(NAGIOS_HOME, CRON_CHECK_TMPFILE)
    with open(_tmp_file, 'wt') as f:
        f.writelines(lines)

    # In cis hardened environments check_ceph_osd_services cannot
    # read _tmp_file due to restrained permissions (#LP1879667).
    # Changing the owner of the file to nagios solves this problem.
    # check_ceph_osd_services.py removes this file, so make
    # sure that we change permissions on a file that exists.
    nagios_uid = getpwnam('nagios').pw_uid
    nagios_gid = getpwnam('nagios').pw_gid
    if os.path.isfile(_tmp_file):
        os.chown(_tmp_file, nagios_uid, nagios_gid)


def run_main():
    # on bionic we can interprocess lock; we don't do it for older platforms
    if fasteners is not None:
        lock = fasteners.InterProcessLock(LOCKFILE)

        if lock.acquire(blocking=False):
            try:
                do_status()
            finally:
                lock.release()
    else:
        do_status()


if __name__ == '__main__':
    run_main()
