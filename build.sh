#!/bin/bash -eux
snapcraft clean
snapcraft
snapcraft push hotsos_1.0_amd64.snap

echo "Don't forget to snapcraft release!"
