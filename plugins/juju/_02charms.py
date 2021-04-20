#!/usr/bin/python3
import glob
import re
import os

from common import (
    plugin_yaml,
)
from juju_common import (
    CHARM_MANIFEST_GLOB,
    JUJU_LIB_PATH,
)

CHARM_VERSIONS = {"charm-versions": []}


def get_charm_versions():
    if not os.path.exists(JUJU_LIB_PATH):
        return

    versions = []
    for entry in glob.glob(os.path.join(JUJU_LIB_PATH, CHARM_MANIFEST_GLOB)):
        for manifest in os.listdir(entry):
            base = os.path.basename(manifest)
            ret = re.compile(r".+_(\S+)-([0-9]+)$").match(base)
            if ret:
                versions.append("{}-{}".format(ret[1], ret[2]))

    if versions:
        CHARM_VERSIONS["charm-versions"] = sorted(versions)


if __name__ == "__main__":
    get_charm_versions()
    if CHARM_VERSIONS:
        plugin_yaml.dump(CHARM_VERSIONS)
