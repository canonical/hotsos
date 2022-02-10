#!/bin/bash

# This script is invoked by cdk.master.leader.file-watcher.service

if [ is-leader ]; then
  leader-set \
    "/root/cdk/basic_auth.csv=$(cat /root/cdk/basic_auth.csv)" \
    "/root/cdk/known_tokens.csv=$(cat /root/cdk/known_tokens.csv)" \
    "/root/cdk/serviceaccount.key=$(cat /root/cdk/serviceaccount.key)"
fi
