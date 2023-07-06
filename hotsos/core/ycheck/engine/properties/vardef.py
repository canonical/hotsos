from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    YDefsSection,
    add_to_property_catalog,
)


@add_to_property_catalog
class YPropertyVarDef(YPropertyMappedOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['vardef']

    @classmethod
    def _override_mapped_member_types(cls):
        """
        In order to be able to have values of type str, int etc we need this to
        be a mapped override even though we are not explicitly using any
        member properties.
        """
        return []

    @property
    def raw_value(self):
        return list(self.content.keys())[0]

    def _is_import_path(self, val):
        return type(val) == str and val.startswith('@')

    @cached_yproperty_attr
    def value(self):
        """
        Value can be a raw type or a string starting with a '@' which indicates
        it it a Python property to be imported/loaded. Imports are done when
        the variable value is accessed for the first time i.e. it is lazy
        loaded.
        """
        val = self.raw_value
        if self._is_import_path(val):
            # NOTE: this path can be a property or a factory.
            val = self.get_property(val[1:])

        return val

    def __repr__(self):
        val = self.raw_value
        lazy_load = self._is_import_path(val)
        return "value={} (type={}, lazy_load={})".format(val, type(val),
                                                         lazy_load)


@add_to_property_catalog
class YPropertyVars(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['vars']

    @cached_yproperty_attr
    def _vardefs(self):
        log.debug("parsing vars section")
        resolved = {}
        for name, content in self.content.items():
            s = YDefsSection(self._override_name, {name: {'vardef': content}},
                             context=self.context)
            for v in s.leaf_sections:
                resolved[v.name] = v.vardef

        log.debug("done: %s", [repr(v) for v in resolved.values()])
        return resolved

    def resolve(self, name):
        log.debug("resolving var '%s'", name)
        if not name:
            raise Exception("attempting to resolve invalid varname '{}'".
                            format(name))

        vardef = self._vardefs.get(name)  # pylint: disable=E1101
        if vardef:
            value = vardef.value
            log.debug("resolved var %s=%s (type=%s)", name, value, type(value))
        else:
            log.warning("could not resolve var %s", name)
            value = None

        return value

    def __iter__(self):
        log.debug("iterating over vars")
        for name, var in self._vardefs.items():  # pylint: disable=E1101
            log.debug("returning var %s", name)
            yield name, var.vardef
