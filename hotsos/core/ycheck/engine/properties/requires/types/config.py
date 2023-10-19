import glob
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    add_to_property_catalog,
    YDefsSection,
    YDefsContext,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    LogicalCollectionHandler,
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    OpsUtils,
    YRequirementTypeBase,
)


class YAssertionAttrs(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['key', 'value', 'section', 'ops', 'allow-unset']

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

    def get_item_result_callback(self, item, grouped=False):
        handlers = self.context.assertions_ctxt['cfg_handlers']
        if not handlers:
            return

        for n, cfg_obj in enumerate(handlers):
            if item.section:
                actual = cfg_obj.get(item.key, section=item.section)
            else:
                actual = cfg_obj.get(item.key)

            _result = item.allow_unset

            ops = item.ops or [['eq', item.value]]
            if actual is not None:
                _result = self.apply_ops(ops, opinput=actual,
                                         normalise_value_types=True)
            log.debug("assertion: %s (%s) %s result=%s",
                      item.key, actual, self.ops_to_str(ops or []),
                      _result)
            if not _result and n < len(handlers) - 1:
                log.debug("assertion is false and there are more configs to "
                          "check so trying next")
                continue

            cache = self.context.assertions_ctxt['cache']
            msg = "{} {}/actual=\"{}\"".format(item.key,
                                               self.ops_to_str(ops or []),
                                               actual)
            if cache.assertion_results is not None:
                cache.set('assertion_results', "{}, {}".
                          format(cache.assertion_results, msg))
            else:
                cache.set('assertion_results', msg)

            # NOTE: This can be useful for single assertion checks but should
            # be used with caution since it will only ever store the last
            # config checked.
            cache.set('key', item.key)
            cache.set('ops', self.ops_to_str(ops or []))
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
    def cfg_handlers(self):
        """
        @return: list of config handlers
        """
        handler = self.content['handler']
        obj = self.get_cls(handler)
        paths = self.content.get('path')
        if not paths:
            log.debug("no config path provided, creating handler %s "
                      "without args", handler)
            return [obj()]

        if type(paths) == str:
            paths = [paths]

        handlers = []
        for path in paths:
            path = os.path.join(HotSOSConfig.data_root, path)
            if os.path.isfile(path):
                handlers.append(obj(path))

            if os.path.isdir(path):
                path = path + '/*'

            for _path in glob.glob(path):
                if os.path.isfile(_path):
                    handlers.append(obj(_path))

        return handlers

    @property
    def assertions(self):
        _assertions = []
        ctxt = YDefsContext({'vars': self.context.vars})
        # make this available to all assertions
        ctxt.assertions_ctxt = {'cfg_handlers': self.cfg_handlers,
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
