#!/bin/bash
# Copyright (C) 2014 Canonical
# All Rights Reserved
# Author: Jacek Nykis <jacek.nykis@canonical.com>

LOCK=/var/lock/ceph-status.lock
lockfile-create -r2 --lock-name $LOCK > /dev/null 2>&1
if [ $? -ne 0 ]; then
    exit 1
fi
trap "rm -f $LOCK > /dev/null 2>&1" exit

DATA_DIR="/var/lib/nagios"
if [ ! -d $DATA_DIR ]; then
    mkdir -p $DATA_DIR
fi

ceph status >${DATA_DIR}/cat-ceph-status.txt
