from hotsos.core.log import log
from hotsos.core.utils import cached_property
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

    @cached_property
    def packaging_helper(self):
        return APTPackageHelper(self.packages_to_check)

    @cached_property
    def installed_versions(self):
        _versions = []
        for p in self.installed:
            _versions.append(self.packaging_helper.get_version(p))

        return _versions

    def package_version_within_ranges(self, pkg, versions):
        result = False
        version = self.packaging_helper.get_version(pkg)
        for item in sorted(versions, key=lambda i: i['max'],
                           reverse=True):
            v_max = str(item['max'])
            v_min = str(item['min'])
            lte_max = version <= DPKGVersionCompare(v_max)
            if v_min:
                lt_broken = version < DPKGVersionCompare(v_min)
            else:
                lt_broken = None

            if lt_broken:
                continue

            if lte_max:
                result = True
            else:
                result = False

            break

        log.debug("package %s=%s within version ranges %s "
                  "(result=%s)", pkg, version, versions, result)
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
