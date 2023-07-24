from functools import cached_property

from hotsos.core.log import log
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DPKGVersionCompare,
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class APTCheckItems(PackageCheckItemsBase):

    # NOTE: the following pylint disable can be removed when we move to newer
    #       pylint.
    @cached_property
    def packaging_helper(self):  # pylint: disable=W0236
        return APTPackageHelper(self.packages_to_check)

    @cached_property
    def installed_versions(self):
        _versions = []
        for p in self.installed:
            _versions.append(self.packaging_helper.get_version(p))

        return _versions

    def package_version_within_ranges(self, pkg, versions):
        result = False
        versions = sorted(versions, key=lambda i: str(i['min']), reverse=True)
        pkg_version = self.packaging_helper.get_version(pkg)
        for item in versions:
            v_min = str(item['min'])
            if 'max' in item:
                v_max = str(item['max'])
                lte_max = pkg_version <= DPKGVersionCompare(v_max)
            else:
                lte_max = True

            if v_min:
                lt_broken = pkg_version < DPKGVersionCompare(v_min)
            else:
                lt_broken = None

            if lt_broken:
                continue

            result = lte_max

            break

        log.debug("package %s=%s within version ranges %s "
                  "(result=%s)", pkg, pkg_version, versions, result)
        return result


class YRequirementTypeAPT(YRequirementTypeBase):
    """ Provides logic to perform checks on APT packages. """

    @classmethod
    def _override_keys(cls):
        return ['apt']

    @property
    @intercept_exception
    def _result(self):
        _result = True
        items = APTCheckItems(self.content)
        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for pkg, versions in items:
                log.debug("package %s installed=%s", pkg, _result)
                if not versions:
                    continue

                _result = items.package_version_within_ranges(pkg, versions)
                # bail at first failure
                if not _result:
                    break
        else:
            log.debug("one or more packages not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            # bail on first fail i.e. if any not installed
            _result = False

        self.cache.set('package', ', '.join(items.installed))
        self.cache.set('version', ', '.join(items.installed_versions))
        log.debug('requirement check: apt %s (result=%s)',
                  ', '.join(items.packages_to_check), _result)
        return _result
