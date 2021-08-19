#!/bin/bash -eux

# require successfull run
tox

# these get created when running units tests so need to remove since they will break hotsos
find plugins -name __pycache__ -type d| xargs -l rm -rf

snapcraft clean --destructive-mode
snapcraft --destructive-mode
snapcraft upload hotsos_1.0_amd64.snap

echo "Don't forget to snapcraft release!"
