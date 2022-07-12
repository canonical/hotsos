#!/bin/bash -eux

# require successful run
tox

snapcraft clean --destructive-mode
snapcraft --destructive-mode
snapcraft upload hotsos_1.0_all.snap

echo "Don't forget to snapcraft release!"
