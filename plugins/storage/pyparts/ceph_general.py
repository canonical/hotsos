from common.checks import APTPackageChecksBase
from common.plugins.storage import (
    CephChecksBase,
    CEPH_PKGS_CORE,
    CEPH_SERVICES_EXPRS,
    StorageChecksBase,
)

YAML_PRIORITY = 0


class CephPackageChecks(StorageChecksBase, APTPackageChecksBase):

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all


class CephServiceChecks(CephChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def __call__(self):
        self.get_running_services_info()


def get_service_checker():
    # Do this way to make it easier to write unit tests.
    return CephServiceChecks(CEPH_SERVICES_EXPRS)


def get_pkg_checker():
    return CephPackageChecks(CEPH_PKGS_CORE)
