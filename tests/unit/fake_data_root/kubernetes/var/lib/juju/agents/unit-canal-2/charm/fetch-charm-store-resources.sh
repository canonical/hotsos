#!/bin/bash
set -eux

# This script will download the resources associated with each charm that
# canal cares about (ie, flannel and calico) from the charm store. By default,
# it will pull charm resources from the edge channel. Call it with
# edge|beta|candidate|stable as the first arg to specify the channel.
#
# If you need to construct new resources from upstream binaries, see the
# build-canal-resources.sh script in this repository.

channel=${1:-}
if [ -z ${channel} ]; then
  channel="edge"
fi

# 'charm' and 'wget' are required
command -v charm >/dev/null 2>&1 || { echo 'charm: command not found'; exit 1; }
command -v wget >/dev/null 2>&1 || { echo 'wget: command not found'; exit 1; }

# list of namespaced charms from which to fetch resources
charms="~containers/flannel ~containers/calico"
for charm in ${charms}; do
  # get the id (charm-revision), stripping any 'cs:' prefix
  charm_id=$(charm show ${charm} -c ${channel} id | grep -o "${charm}.*" | sed -e 's/^cs://')

  # get our resources, skipping potential header rows. list looks like:
  #   [Service]
  #   RESOURCE      REVISION
  #   flannel-amd64 3
  #   flannel-arm64 1
  #   flannel-s390x 3
  resources=$(charm list-resources ${charm_id} | grep -v "\[Service\]" | tail -n +2 | sed -e '/^$/d')

  # construct a url and wget each resource. each resource line looks like:
  #    flannel-amd64 3
  IFS=$'\n'
  for res in $resources; do
    res_name=$(echo $res | awk '{print $1}')
    res_rev=$(echo $res | awk '{print $2}')
    res_url="https://api.jujucharms.com/charmstore/v5/${charm_id}/resource/${res_name}/${res_rev}"
    wget ${res_url} -O ${res_name}.tar.gz
  done
  unset IFS
done
