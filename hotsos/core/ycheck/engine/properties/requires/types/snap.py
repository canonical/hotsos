from hotsos.core.log import log
from hotsos.core.host_helpers import SnapPackageChecksBase
from hotsos.core.ycheck.engine.properties.requires import YRequirementTypeBase


class YRequirementTypeSnap(YRequirementTypeBase):
    """ Provides logic to perform checks on snap packages. """

    @classmethod
    def _override_keys(cls):
        return ['snap']

    @property
    def _result(self):
        pkg = self.content
        _result = pkg in SnapPackageChecksBase(core_snaps=[pkg]).all
        log.debug('requirement check: snap %s (result=%s)', pkg, _result)
        self.cache.set('package', pkg)
        return _result
