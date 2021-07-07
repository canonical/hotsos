import glob
import re
import os

from juju_common import (
    CHARM_MANIFEST_GLOB,
    JujuChecksBase,
    JUJU_LIB_PATH,
)

YAML_PRIORITY = 1


class JujuCharmChecks(JujuChecksBase):

    def get_charm_versions(self):
        if not os.path.exists(JUJU_LIB_PATH):
            return

        versions = []
        for entry in glob.glob(os.path.join(JUJU_LIB_PATH,
                                            CHARM_MANIFEST_GLOB)):
            for manifest in os.listdir(entry):
                base = os.path.basename(manifest)
                ret = re.compile(r".+_(\S+)-([0-9]+)$").match(base)
                if ret:
                    versions.append("{}-{}".format(ret[1], ret[2]))

        if versions:
            self._output["charm-versions"] = sorted(versions)

    def __call__(self):
        self.get_charm_versions()
