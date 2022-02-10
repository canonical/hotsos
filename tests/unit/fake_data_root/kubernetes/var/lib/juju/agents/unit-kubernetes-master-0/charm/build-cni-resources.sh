#!/usr/bin/env bash

set -eux

# When changing CNI_VERSION, it should be updated in both
# charm-kubernetes-master/build-cni-resources.sh and
# charm-kubernetes-worker/build-cni-resources.sh
CNI_VERSION="${CNI_VERSION:-v0.7.5}"
ARCH="${ARCH:-amd64 arm64 s390x}"

build_script_commit="$(git show --oneline -q)"
temp_dir="$(readlink -f build-cni-resources.tmp)"
rm -rf "$temp_dir"
mkdir "$temp_dir"
(cd "$temp_dir"
  git clone https://github.com/containernetworking/plugins.git cni-plugins \
    --branch "$CNI_VERSION" \
    --depth 1

  # Grab the user id and group id of this current user.
  GROUP_ID=$(id -g)
  USER_ID=$(id -u)

  for arch in $ARCH; do
    echo "Building cni $CNI_VERSION for $arch"
    rm -f cni-plugins/bin/*
    docker run \
      --rm \
      -e GOOS=linux \
      -e GOARCH="$arch" \
      -v "$temp_dir"/cni-plugins:/cni \
      golang:1.15 \
      /bin/bash -c "cd /cni && ./build.sh && chown -R ${USER_ID}:${GROUP_ID} /cni"

    (cd cni-plugins/bin
      echo "cni-$arch $CNI_VERSION" >> BUILD_INFO
      echo "Built $(date)" >> BUILD_INFO
      echo "build script commit: $build_script_commit" >> BUILD_INFO
      echo "cni-plugins commit: $(git show --oneline -q)" >> BUILD_INFO
      tar -czf "$temp_dir/cni-$arch.tgz" .
    )
  done
)
mv "$temp_dir"/cni-*.tgz .
rm -rf "$temp_dir"
