from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeWithOpsBase,
)


class YPropertyVarOps(YRequirementTypeWithOpsBase):

    @classmethod
    def _override_keys(cls):
        return ['varops']

    @property
    def name(self):
        return self.content[0][0]

    @property
    def ops(self):
        return self.content[1:]

    def _apply_ops(self):
        actual = self.resolve_var(self.name)
        result = self.apply_ops(self.ops, opinput=actual)
        log.debug('requirement check: varref %s %s (result=%s)',
                  actual, self.ops_to_str(self.ops), result)
        self.cache.set('ops', self.ops_to_str(self.ops))
        self.cache.set('value', actual)
        self.cache.set('name', self.name)
        return result

    @property
    @intercept_exception
    def _result(self):
        return self._apply_ops()
