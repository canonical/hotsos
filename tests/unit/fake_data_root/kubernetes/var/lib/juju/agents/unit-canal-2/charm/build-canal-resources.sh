#!/bin/bash
set -eux

# This script will use the build scripts for the calico and flannel charms
# to construct resources needed for canal.
#
# If you want to fetch existing resources from the calico and flannel charms
# in the charm store, see fetch-charm-store-resources.sh in this repository.

ARCH=${ARCH:-"amd64 arm64"}
CALICO_COMMIT="5dab860987023b9b2570870b0f37d958bb7fd9b2"
FLANNEL_COMMIT="c4b1f996c9813567c5a60502e4ee14bafb4299e8"

# 'git' is required
command -v git >/dev/null 2>&1 || { echo 'git: command not found'; exit 1; }

calico_repo="https://github.com/juju-solutions/layer-calico.git"
flannel_repo="https://github.com/juju-solutions/charm-flannel.git"
canal_root="${PWD}"
canal_temp="${canal_root}/temp"

test -d "${canal_temp}" && rm -rf "${canal_temp}"
mkdir -p "${canal_temp}"

# calico
git clone $calico_repo "${canal_temp}/calico"
pushd ${canal_temp}/calico
git checkout "$CALICO_COMMIT"
./build-calico-resource.sh
mv calico-*.gz ${canal_root}
popd

# flannel
git clone $flannel_repo "${canal_temp}/flannel"
pushd ${canal_temp}/flannel
git checkout "$FLANNEL_COMMIT"
ARCH="$ARCH" ./build-flannel-resources.sh
mv flannel-*.gz ${canal_root}
popd

test -d "${canal_temp}" && rm -rf "${canal_temp}"

touch calico-node-image.tar.gz
