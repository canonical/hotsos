from functools import cached_property

from hotsos.core.log import log
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DPKGVersion,
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class APTCheckItems(PackageCheckItemsBase):
    """
    Implementation for check items on apt package properties.
    """
    @cached_property
    def packaging_helper(self):
        return APTPackageHelper(self.packages_to_check)

    @cached_property
    def installed_versions(self):
        return [self.packaging_helper.get_version(p) for p in self.installed]


class YRequirementTypeAPT(YRequirementTypeBase):
    """
    Apt requires type property. Provides support for defining the apt package
    requires type to perform checks on APT packages.
    """
    override_keys = ['apt']
    override_autoregister = True

    @property
    @intercept_exception
    def _result(self):
        # pylint: disable=duplicate-code
        _result = True
        items = APTCheckItems(self.content)

        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for pkg, versions in items:
                log.debug("package %s installed=%s", pkg, _result)
                if not versions:
                    continue
                pkg_version = items.packaging_helper.get_version(pkg)
                _result = DPKGVersion.is_version_within_ranges(pkg_version,
                                                               versions)
                # bail at first failure
                if not _result:
                    break
        else:
            log.debug("one or more packages not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            # bail on first fail i.e. if any not installed
            _result = False

        self.cache.set('package', ', '.join(items.installed))
        self.cache.set('version', ', '.join([
            str(x) for x in items.installed_versions]))
        log.debug('requirement check: apt %s (result=%s)',
                  ', '.join(items.packages_to_check), _result)
        return _result
