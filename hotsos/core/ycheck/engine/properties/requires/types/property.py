from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeWithOpsBase,
)


class YRequirementTypeProperty(YRequirementTypeWithOpsBase):
    """ Provides logic to perform checks on Python Properties. """

    @classmethod
    def _override_keys(cls):
        return ['property']

    @property
    @intercept_exception
    def _result(self):
        if type(self.content) != dict:
            path = self.content
        else:
            path = self.content['path']

        actual = self.get_property(path)
        result = self.apply_ops(self.ops, opinput=actual)
        log.debug('requirement check: property %s %s (result=%s)',
                  path, self.ops_to_str(self.ops), result)
        self.cache.set('property', path)
        self.cache.set('ops', self.ops_to_str(self.ops))
        self.cache.set('value_actual', actual)
        return result
