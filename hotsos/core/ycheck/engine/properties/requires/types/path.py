import os

from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.input import YPropertyInputBase
from hotsos.core.ycheck.engine.properties.requires import YRequirementTypeBase


class YRequirementTypePath(YPropertyInputBase, YRequirementTypeBase):
    """ Provides logic to perform checks on filesystem paths. """

    @classmethod
    def _override_keys(cls):
        # We can't use 'input' since that property is already used.
        return ['path']

    @property
    def options(self):
        """
        Override this since we never want to have all-logs applied since
        it is not relevant in checking if the path exists.
        """
        _options = super().options
        _options['disable-all-logs'] = True
        return _options

    @property
    def _result(self):
        _result = False
        # first try fs path in its raw format i.e. without ALL_LOGS applied. if
        # that is not available try the parsed path which would be command.
        if self.path and os.path.exists(self.path):
            _result = True

        log.debug('requirement check: path %s (result=%s)', self.path, _result)
        self.cache.set('path', self.path)
        return _result
