#!/usr/bin/env python

# Copyright (C) 2014 Canonical
# All Rights Reserved
# Author: Jacek Nykis <jacek.nykis@canonical.com>

import re
import argparse
import subprocess
import nagios_plugin


def check_ceph_status(args):
    if args.status_file:
        nagios_plugin.check_file_freshness(args.status_file, 3600)
        with open(args.status_file, "rt", encoding='UTF-8') as f:
            lines = f.readlines()
    else:
        lines = (subprocess
                 .check_output(["ceph", "status"])
                 .decode('UTF-8')
                 .split('\n'))
    status_data = dict(
        line.strip().split(' ', 1) for line in lines if len(line) > 1)

    if ('health' not in status_data or
            'monmap' not in status_data or
            'osdmap' not in status_data):
        raise nagios_plugin.UnknownError('UNKNOWN: status data is incomplete')

    if status_data['health'] != 'HEALTH_OK':
        msg = 'CRITICAL: ceph health status: "{}'.format(status_data['health'])
        if (len(status_data['health'].split(' '))) == 1:
            a = iter(lines)
            for line in a:
                if re.search('health', line) is not None:
                    msg1 = next(a)
                    msg += " "
                    msg += msg1.strip()
                    break
        msg += '"'
        raise nagios_plugin.CriticalError(msg)

    osds = re.search(r"^.*: (\d+) osds: (\d+) up, (\d+) in",
                     status_data['osdmap'])
    if osds.group(1) > osds.group(2):  # not all OSDs are "up"
        msg = 'CRITICAL: Some OSDs are not up. Total: {}, up: {}'.format(
            osds.group(1), osds.group(2))
        raise nagios_plugin.CriticalError(msg)
    print("All OK")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check ceph status')
    parser.add_argument('-f',
                        '--file',
                        dest='status_file',
                        default=False,
                        help='Optional file with "ceph status" output')
    args = parser.parse_args()
    nagios_plugin.try_check(check_ceph_status, args)
