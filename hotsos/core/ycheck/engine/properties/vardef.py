from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import YPropertyOverrideBase


class YPropertyVars(YPropertyOverrideBase):
    """
    Vars property. Provides support for defining variables in YAML e.g.

    vars:
      var1: val1
      var2: @property1

    where val1 is a literal and property2 is an import path.
    """
    override_keys = ['vars']
    _allow_subtree = False

    @staticmethod
    def _is_import_path(value):
        return isinstance(value, str) and value.startswith('@')

    def resolve(self, name):
        """
        Value can be a raw type or a string starting with a '@' which indicates
        it it a Python property to be imported/loaded. Imports are done when
        the variable value is accessed for the first time i.e. it is lazy
        loaded.
        """
        log.debug("resolving var '%s'", name)
        if not name:
            raise NameError(
                f"attempting to resolve invalid varname '{name}'")

        if hasattr(self, name):
            value = getattr(self, name)
            if self._is_import_path(value):
                # NOTE: this path can be a property or a factory.
                value = self.get_property(value[1:])

            log.debug("resolved var %s=%s (type=%s)", name, value, type(value))
        else:
            log.warning("could not resolve var %s", name)
            value = None

        return value

    def __iter__(self):
        log.debug("iterating over vars")
        for name, var in self._vardefs.items():
            log.debug("returning var %s", name)
            yield name, var.vardef
