from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import YRequirementTypeBase


class YRequirementTypeProperty(YRequirementTypeBase):
    """ Provides logic to perform checks on Python Properties. """

    @classmethod
    def _override_keys(cls):
        return ['property']

    @property
    def _result(self):
        default_ops = [['truth']]
        if type(self.content) != dict:
            path = self.content
            # default is get bool (True/False) for value
            ops = default_ops
        else:
            path = self.content['path']
            ops = self.content.get('ops', default_ops)

        actual = self.get_property(path)
        _result = self.apply_ops(ops, input=actual)
        log.debug('requirement check: property %s %s (result=%s)',
                  path, self.ops_to_str(ops), _result)
        self.cache.set('property', path)
        self.cache.set('ops', self.ops_to_str(ops))
        self.cache.set('value_actual', actual)
        return _result
