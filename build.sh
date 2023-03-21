#!/bin/bash -eux
build_type=${1:-pypi}

# require successful run
tox

if [[ $build_type == snap ]]; then
    snapcraft clean --destructive-mode
    snapcraft --destructive-mode
    snapcraft upload hotsos_1.0_amd64.snap
elif [[ $build_type == pypi ]]; then
    git rev-parse --short HEAD > hotsos/.repo-info
    export GIT_BUILD_VERSION=`git describe --tags`
    python3 -m build
    #python3 -m twine upload dist/hotsos*
fi
