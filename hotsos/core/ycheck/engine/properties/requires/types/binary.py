from functools import cached_property

from hotsos.core.log import log
from hotsos.core.host_helpers import (
    DPKGVersion
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase
)


class BinCheckItems(PackageCheckItemsBase):
    """
    By default we use the APT version checks logic for binary versions. At some
    point in the future we may want to support overriding this.
    """

    def __init__(self, *args, bin_handler=None, **kwargs):
        self.bin_handler = bin_handler
        super().__init__(*args, **kwargs)

    @cached_property
    def packaging_helper(self):
        return self.bin_handler()

    @cached_property
    def installed_versions(self):
        _versions = []
        for p in self.installed:
            _versions.append(self.packaging_helper.get_version(p))

        return _versions


class YRequirementTypeBinary(YRequirementTypeBase):
    _override_keys = ['binary']
    _overrride_autoregister = True

    @property
    def _bin_info(self):
        if hasattr(self, 'name'):
            return {self.name: None}

        return {k: v for k, v in self.content.items() if k not in ['handler']}

    @property
    @intercept_exception
    def _result(self):
        items = BinCheckItems(self._bin_info,
                              bin_handler=self.get_cls(self.handler))

        _result = True
        # bail on first fail i.e. if any not installed
        if not items.not_installed:
            for binary, versions in items:
                log.debug("binary %s installed=%s", binary, _result)
                if not versions:
                    continue
                version = items.packaging_helper.get_version(binary)
                _result = DPKGVersion.is_version_within_ranges(version,
                                                               versions)
                # bail at first failure
                if not _result:
                    break
        else:
            log.debug("one or more binary not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            # bail on first fail i.e. if any not installed
            _result = False

        self.cache.set('binary', ', '.join(items.installed))
        self.cache.set('version', ', '.join([
            str(x) for x in items.installed_versions]))
        log.debug('requirement check: %s %s (result=%s)',
                  self.__class__.__name__,
                  ', '.join(items.packages_to_check), _result)
        return _result
