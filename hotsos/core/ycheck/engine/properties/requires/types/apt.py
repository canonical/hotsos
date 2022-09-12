from hotsos.core.log import log
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DPKGVersionCompare,
)
from hotsos.core.ycheck.engine.properties.requires import YRequirementTypeBase


class YRequirementTypeAPT(YRequirementTypeBase):
    """ Provides logic to perform checks on APT packages. """

    @classmethod
    def _override_keys(cls):
        return ['apt']

    def _package_version_within_ranges(self, pkg_version, versions):
        for item in sorted(versions, key=lambda i: i['max'],
                           reverse=True):
            v_max = str(item['max'])
            v_min = str(item['min'])
            lte_max = pkg_version <= DPKGVersionCompare(v_max)
            if v_min:
                lt_broken = pkg_version < DPKGVersionCompare(v_min)
            else:
                lt_broken = None

            if lt_broken:
                continue

            if lte_max:
                return True
            else:
                return False

        return False

    @property
    def _result(self):
        # Value can be a package name or dict that provides more
        # information about the package or list of packages.
        if type(self.content) == dict:
            packages = self.content
            packages_under_test = list(packages.keys())
        elif type(self.content) == list:
            packages = {p: None for p in self.content}
            packages_under_test = self.content
        else:
            packages = {self.content: None}
            packages_under_test = [self.content]

        versions_actual = []
        apt_info = APTPackageHelper(packages_under_test)
        for pkg, versions in packages.items():
            _result = apt_info.is_installed(pkg) or False
            if _result:
                pkg_ver = apt_info.get_version(pkg)
                versions_actual.append(pkg_ver)
                if versions:
                    _result = self._package_version_within_ranges(pkg_ver,
                                                                  versions)
                    log.debug("package %s=%s within version ranges %s "
                              "(result=%s)", pkg, pkg_ver, versions, _result)

            log.debug("package %s installed=%s", pkg, _result)
            # bail at first failure
            if not _result:
                break

        self.cache.set('package', ', '.join(packages.keys()))
        self.cache.set('version', ', '.join(versions_actual))
        log.debug('requirement check: apt %s (result=%s)', pkg, _result)
        return _result
