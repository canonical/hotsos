from core.checks import APTPackageChecksBase
from core.plugins.storage.ceph import (
    CephServiceChecksBase,
    CEPH_PKGS_CORE,
    CEPH_PKGS_OTHER,
)

YAML_PRIORITY = 0


class CephPackageChecks(CephServiceChecksBase, APTPackageChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(core_pkgs=CEPH_PKGS_CORE, other_pkgs=CEPH_PKGS_OTHER)

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all_formatted


class CephServiceChecks(CephServiceChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def __call__(self):
        self._output['release'] = self.release_name
        self.get_running_services_info()
