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
    def value(self):
        val = list(self.content.keys())[0]
        if type(val) == str and val.startswith('@'):
            val = self.get_property(val[1:])

        return val


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
            s = YDefsSection(self._override_name, {name: {'vardef': content}})
            for v in s.leaf_sections:
                resolved[v.name] = v.vardef

        log.debug("done: %s", [v.value for v in resolved.values()])
        return resolved

    def resolve(self, name):
        log.debug("resolving var %s", name)
        vardef = self._vardefs.get(name)
        if vardef:
            value = vardef.value
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
