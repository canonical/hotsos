import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    OpsUtils,
    YRequirementTypeBase,
)
from hotsos.core.ycheck.engine.properties.common import (
    add_to_property_catalog,
    YDefsSection,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    LogicalCollectionHandler,
)


class YAssertionAttrs(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['key', 'section', 'ops', 'allow-unset']

    @property
    def ops(self):
        """
        This is a list so needs its own property.
        """
        return self.content


class YAssertion(YPropertyMappedOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['assertion']

    @classmethod
    def _override_mapped_member_types(cls):
        return [YAssertionAttrs]


class YPropertyAssertionsBase(YPropertyMappedOverrideBase,
                              LogicalCollectionHandler,
                              OpsUtils):

    @classmethod
    def _override_mapped_member_types(cls):
        return [YAssertion]

    def run_single(self, item):
        final_results = []
        log.debug("running %s assertions", len(item))
        for assertion in item:
            result = self.get_item_result_callback(assertion)
            final_results.append(result)

        return final_results

    def get_item_result_callback(self, item):
        cfg_obj = self.context.cfg_obj
        if item.section:
            actual = cfg_obj.get(item.key, section=item.section)
        else:
            actual = cfg_obj.get(item.key)

        _result = item.allow_unset
        if item.ops and actual is not None:
            _result = self.apply_ops(item.ops, input=actual,
                                     normalise_value_types=True)
        log.debug("assertion: %s (%s) %s result=%s",
                  item.key, actual, self.ops_to_str(item.ops or []), _result)

        # This is a bit iffy since it only gives us the final config
        # assertion checked.
        cache = self.context.cache
        cache.set('key', item.key)
        cache.set('ops', self.ops_to_str(item.ops or []))
        cache.set('value_actual', actual)

        return _result

    @property
    def passes(self):
        log.debug("running assertion set")
        try:
            result = self.run_collection()
        except Exception:
            log.exception("exception caught during run_collection:")
            raise

        return result


class YPropertyAssertionsLogicalGroupsExtension(YPropertyAssertionsBase):

    @classmethod
    def _override_keys(cls):
        return LogicalCollectionHandler.VALID_GROUP_KEYS


@add_to_property_catalog
class YPropertyAssertions(YPropertyAssertionsBase):

    @classmethod
    def _override_keys(cls):
        return ['assertions']

    @classmethod
    def _override_mapped_member_types(cls):
        return super()._override_mapped_member_types() + \
                    [YPropertyAssertionsLogicalGroupsExtension]


class YRequirementTypeConfig(YRequirementTypeBase):
    """ Provides logic to perform checks on configuration. """

    @classmethod
    def _override_keys(cls):
        return ['config']

    @property
    def cfg(self):
        handler = self.content['handler']
        obj = self.get_cls(handler)
        path = self.content.get('path')
        if path:
            path = os.path.join(HotSOSConfig.DATA_ROOT, path)
            return obj(path)

        return obj()

    @property
    def assertions(self):
        _assertions = []
        section = YDefsSection('config_assertions',
                               {'assertions': self.content.get('assertions')})
        for leaf in section.leaf_sections:
            leaf.assertions.context.set('cfg_obj', self.cfg)
            leaf.assertions.context.set('cache', self.cache)
            _assertions.append(leaf.assertions.passes)

        return _assertions

    @property
    def _result(self):
        return all(self.assertions)
