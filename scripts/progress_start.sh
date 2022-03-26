#!/bin/bash -u
{
progress_chars='-\|/'

_cleanup ()
{
    echo -e "\b " 1>&2
    exit
}
trap _cleanup HUP

i=0
while true; do
    i=$(((i+1) % ${#progress_chars}))
    printf "\b${progress_chars:$i:1}" 1>&2
    sleep .1
done
} &
echo $! > $PROGRESS_PID_PATH
