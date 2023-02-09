from hotsos.core.log import log
from hotsos.core.utils import cached_property
from hotsos.core.host_helpers import SnapPackageHelper
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
    PackageCheckItemsBase,
)


class SnapCheckItems(PackageCheckItemsBase):

    @cached_property
    def packaging_helper(self):
        return SnapPackageHelper(core_snaps=self.packages_to_check)


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
