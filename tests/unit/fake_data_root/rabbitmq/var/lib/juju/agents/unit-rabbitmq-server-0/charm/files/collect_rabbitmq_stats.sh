#!/bin/bash
# Copyright (C) 2011, 2014 Canonical
# All Rights Reserved
# Author: Liam Young, Jacek Nykis

# Produce a queue data for a given vhost. Useful for graphing and Nagios checks
LOCK=/var/lock/rabbitmq-gather-metrics.lock
# Check for a lock file and if not, create one
lockfile-create -r2 --lock-name $LOCK > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Failed to create lockfile: $LOCK."
    exit 1
fi
trap "rm -f $LOCK > /dev/null 2>&1" exit

# Required to fix the bug about start-stop-daemon not being found in
# rabbitmq-server 2.7.1-0ubuntu4.
# '/usr/sbin/rabbitmqctl: 33: /usr/sbin/rabbitmqctl: start-stop-daemon: not found'
export PATH=${PATH}:/sbin/

if [ -f /var/lib/rabbitmq/pids ]; then
    RABBIT_PID=$(grep "{rabbit\@${HOSTNAME}," /var/lib/rabbitmq/pids | sed -e 's!^.*,\([0-9]*\).*!\1!')
elif [ -f /var/run/rabbitmq/pid ]; then
    RABBIT_PID=$(cat /var/run/rabbitmq/pid)
elif [ -f /var/lib/rabbitmq/mnesia/rabbit\@${HOSTNAME}.pid ]; then
    # Vivid and later
    RABBIT_PID=$(cat /var/lib/rabbitmq/mnesia/rabbit\@${HOSTNAME}.pid)
else
    echo "No PID file found"
    exit 3
fi
DATA_DIR="/var/lib/rabbitmq/data"
DATA_FILE="${DATA_DIR}/$(hostname -s)_queue_stats.dat"
LOG_DIR="/var/lib/rabbitmq/logs"
RABBIT_STATS_DATA_FILE="${DATA_DIR}/$(hostname -s)_general_stats.dat"
NOW=$(date +'%s')
HOSTNAME=$(hostname -s)
MNESIA_DB_SIZE=$(du -sm /var/lib/rabbitmq/mnesia | cut -f1)
RABBIT_RSS=$(ps -p $RABBIT_PID -o rss=)
if [ ! -d $DATA_DIR ]; then
    mkdir -p $DATA_DIR
fi
if [ ! -d $LOG_DIR ]; then
    mkdir -p $LOG_DIR
fi
TMP_DATA_FILE=$(mktemp -p ${DATA_DIR})
echo "#Vhost Name Messages_ready Messages_unacknowledged Messages Consumers Memory Time" > ${TMP_DATA_FILE}
/usr/sbin/rabbitmqctl -q list_vhosts | \
while read VHOST; do
    /usr/sbin/rabbitmqctl -q list_queues -p $VHOST name messages_ready messages_unacknowledged messages consumers memory | \
    awk "{print \"$VHOST \" \$0 \" $(date +'%s') \"}" >> ${TMP_DATA_FILE} 2>${LOG_DIR}/list_queues.log
done
mv ${TMP_DATA_FILE} ${DATA_FILE}
chmod 644 ${DATA_FILE}
echo "mnesia_size: ${MNESIA_DB_SIZE}@$NOW" > $RABBIT_STATS_DATA_FILE
echo "rss_size: ${RABBIT_RSS}@$NOW" >> $RABBIT_STATS_DATA_FILE
