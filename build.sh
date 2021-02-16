#!/bin/bash -eux

# these get created when running units tests so need to remove since they will break hotsos
find plugins -name __pycache__ -type d| xargs -l rm -rf

snapcraft clean
snapcraft
snapcraft push hotsos_1.0_amd64.snap

echo "Don't forget to snapcraft release!"
