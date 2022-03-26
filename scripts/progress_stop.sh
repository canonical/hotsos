#!/bin/bash -u
if [[ -r $PROGRESS_PID_PATH ]]; then
    kill -s HUP `cat $PROGRESS_PID_PATH` &>/dev/null
    while [[ -r /proc/`cat $PROGRESS_PID_PATH` ]]; do
        sleep .1
    done
    rm $PROGRESS_PID_PATH
fi

