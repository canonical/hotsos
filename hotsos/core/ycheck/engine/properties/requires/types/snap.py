from hotsos.core.log import log
from hotsos.core.utils import cached_property
from hotsos.core.host_helpers import SnapPackageHelper
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    CheckItemsBase,
    YRequirementTypeBase,
)


class SnapCheckItems(CheckItemsBase):

    @cached_property
    def packages_to_check(self):
        return [item[0] for item in self]

    @cached_property
    def _snap_info(self):
        return SnapPackageHelper(core_snaps=self.packages_to_check)

    @cached_property
    def installed(self):
        _installed = []
        for p in self.packages_to_check:
            if self._snap_info.is_installed(p):
                _installed.append(p)

        return _installed

    @cached_property
    def not_installed(self):
        _all = self.packages_to_check
        return set(self.installed).symmetric_difference(_all)


class YRequirementTypeSnap(YRequirementTypeBase):
    """ Provides logic to perform checks on snap packages. """

    @classmethod
    def _override_keys(cls):
        return ['snap']

    @property
    @intercept_exception
    def _result(self):
        _result = True
        items = SnapCheckItems(self.content)
        if items.not_installed:
            log.debug("one or more packages not installed so returning False "
                      "- %s", ', '.join(items.not_installed))
            _result = False

        log.debug('requirement check: snap(s) %s (result=%s)',
                  ', '.join(items.installed), _result)
        self.cache.set('package', ', '.join(items.installed))
        return _result
