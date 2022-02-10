#!/usr/bin/env python3

# Copyright (C) 2018 Canonical
# All Rights Reserved
# Author: Alex Kavanagh <alex.kavanagh@canonical.com>

import os
import sys

CRON_CHECK_TMPFILE = 'ceph-osd-checks'
NAGIOS_HOME = '/var/lib/nagios'

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3


def run_main():
    """Process the CRON_CHECK_TMP_FILE and see if any line is not OK.

    If a line is not OK, the main returns STATE_CRITICAL.
    If there are no lines, or the file doesn't exist, it returns STATE_UNKNOWN
    Otherwise it returns STATE_OK.

    :returns: nagios state 0,2 or 3
    """
    _tmp_file = os.path.join(NAGIOS_HOME, CRON_CHECK_TMPFILE)

    if not os.path.isfile(_tmp_file):
        print("File '{}' doesn't exist".format(_tmp_file))
        return STATE_UNKNOWN

    try:
        with open(_tmp_file, 'rt') as f:
            lines = f.readlines()
    except Exception as e:
        print("Something went wrong reading the file: {}".format(str(e)))
        return STATE_UNKNOWN

    # now remove the file in case the next check fails.
    try:
        os.remove(_tmp_file)
    except Exception:
        pass

    if not lines:
        print("checked status file is empty: {}".format(_tmp_file))
        return STATE_UNKNOWN

    # finally, check that the file contains all ok lines.  Unfortunately, it's
    # not consistent across releases, but what is consistent is that the check
    # command in the collect phase does fail, and so the start of the line is
    # 'Failed'
    state = STATE_OK
    for line in lines:
        print(line, end='')
        if line.startswith('Failed'):
            state = STATE_CRITICAL

    return state


if __name__ == '__main__':
    sys.exit(run_main())
