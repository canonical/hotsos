import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    OpsUtils,
    YRequirementTypeBase,
)
from hotsos.core.ycheck.engine.properties.common import (
    add_to_property_catalog,
    YDefsSection,
    YDefsContext,
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

    @property
    def and_group_stop_on_first_false(self):
        """
        Override the default behaviour of LogicalCollectionHandler AND groups.

        We want to always execute all member of all logical op groups so that
        we can have their results in the cached assertion_results.
        """
        return False

    def get_item_result_callback(self, item, is_default_group=False):
        cfg_obj = self.context.assertions_ctxt['cfg_obj']
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

        cache = self.context.assertions_ctxt['cache']
        msg = "{} {}/actual=\"{}\"".format(item.key,
                                           self.ops_to_str(item.ops or []),
                                           actual)
        if cache.assertion_results is not None:
            cache.set('assertion_results', "{}, {}".
                      format(cache.assertion_results, msg))
        else:
            cache.set('assertion_results', msg)

        # NOTE: This can be useful for single assertion checks but should be
        # used with caution since it will only ever store the last config
        # checked.
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
            path = os.path.join(HotSOSConfig.data_root, path)
            return obj(path)

        return obj()

    @property
    def assertions(self):
        _assertions = []
        ctxt = YDefsContext()
        # make this available to all assertions
        ctxt.assertions_ctxt = {'cfg_obj': self.cfg,
                                'cache': self.cache}
        section = YDefsSection('config_assertions',
                               {'assertions': self.content.get('assertions')},
                               context=ctxt)
        for leaf in section.leaf_sections:
            _assertions.append(leaf.assertions.passes)

        return _assertions

    @property
    @intercept_exception
    def _result(self):
        return all(self.assertions)
