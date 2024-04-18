import os

from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.inputdef import YPropertyInputBase
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeBase,
)


class YRequirementTypePath(YPropertyInputBase, YRequirementTypeBase):
    """ Provides logic to perform checks on filesystem paths. """
    _override_keys = ['path']
    _overrride_autoregister = True

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
    @intercept_exception
    def _result(self):
        _result = True
        not_found = None
        for path in self.paths:
            if not os.path.exists(path):
                not_found = path
                _result = False
                break

        log.debug('requirement check: path %s (result=%s)', not_found,
                  _result)
        self.cache.set('path_not_found', not_found)
        self.cache.set('paths', self.paths)
        return _result
