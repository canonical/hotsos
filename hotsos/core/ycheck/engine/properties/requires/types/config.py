import glob
import os
from functools import cached_property

from propertree.propertree2 import PTreeLogicalGrouping
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YDefsSection,
    YDefsContext,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
)
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    OpsUtils,
    YRequirementTypeBase,
)


class YConfigAssertionAttrs(YPropertyOverrideBase):
    """ Logic implementation for config assertion attributes. """
    override_keys = ['key', 'value', 'section', 'ops', 'allow-unset']

    def __bool__(self):
        return bool(self.content)

    def __str__(self):
        return str(self.content)

    @property
    def ops(self):
        """
        This is a list so needs its own property.
        """
        return self.content


class YConfigAssertion(OpsUtils, YPropertyMappedOverrideBase):
    """ Assertion property. Implements the config assertion property used to
    define an assertion on config file contents. """
    override_keys = ['assertion']
    override_members = [YConfigAssertionAttrs]

    @cached_property
    def attrs(self):
        _attrs = {'key': str(self.key), 'allow_unset': False, 'value': None,  # noqa, pylint: disable=E1101
                  'section': None}
        if self.value is not None:  # pylint: disable=E1101
            if isinstance(self.value, bool):  # pylint: disable=E1101
                value = self.value  # pylint: disable=E1101
            else:
                try:
                    value = int(self.value)  # pylint: disable=E1101
                except TypeError:
                    value = str(self.value)  # pylint: disable=E1101

            _attrs['value'] = value

        if self.allow_unset is not None:  # pylint: disable=E1101
            _attrs['allow_unset'] = bool(self.allow_unset)  # noqa, pylint: disable=E1101

        if self.section is not None:  # pylint: disable=E1101
            _attrs['section'] = str(self.section)  # pylint: disable=E1101

        if self.ops:  # pylint: disable=E1101
            _attrs['ops'] = self.ops.ops  # pylint: disable=E1101
        else:
            _attrs['ops'] = [['eq', _attrs['value']]]

        return _attrs

    @property
    def result(self):
        handlers = self.context.assertions_ctxt['cfg_handlers']
        if not handlers:
            log.debug("no handlers found, assuming paths do not exist - "
                      "returning False")
            return False

        key = self.attrs['key']
        value = self.attrs['value']
        section = self.attrs['section']
        ops = self.attrs['ops']
        allow_unset = self.attrs['allow_unset']

        log.debug("%s: key=%s, value=%s, section=%s, ops=%s",
                  self.__class__.__name__, key, value, section, ops)
        for n, cfg_obj in enumerate(handlers):
            if section:
                actual = cfg_obj.get(key, section=section)
            else:
                actual = cfg_obj.get(key)

            _result = allow_unset
            if actual is not None:
                _result = self.apply_ops(ops, opinput=actual,
                                         normalise_value_types=True)
            log.debug("assertion: %s (%s) %s result=%s",
                      key, actual, self.ops_to_str(ops or []),
                      _result)
            if not _result and n < len(handlers) - 1:
                log.debug("assertion is false and there are more configs to "
                          "check so trying next")
                continue

            cache = self.context.assertions_ctxt['cache']
            msg = f"{key} {self.ops_to_str(ops or [])}/actual=\"{actual}\""
            if cache.assertion_results is not None:
                cache.set('assertion_results',
                          f"{cache.assertion_results}, {msg}")
            else:
                cache.set('assertion_results', msg)

            # NOTE: This can be useful for single assertion checks but should
            # be used with caution since it will only ever store the last
            # config checked.
            cache.set('key', key)
            cache.set('ops', self.ops_to_str(ops or []))
            cache.set('value_actual', actual)

        return _result


class AssertionsLogicalGrouping(PTreeLogicalGrouping):
    """ Logical grouping implementation for assertions. """
    override_autoregister = False

    @classmethod
    def and_stop_on_first_false(cls):
        """
        Override the default behaviour of PTreeLogicalGrouping AND groups.

        We want to always execute all member of all logical op groups so that
        we can have their results in the cached assertion_results.
        """
        return False

    def get_items(self):
        log.debug("%s: fetching assertion items", self.__class__.__name__)
        return super().get_items()

    @staticmethod
    def fetch_item_result(item):
        result = item.result
        log.debug("%s: %s result=%s", AssertionsLogicalGrouping.__name__,
                  item.__class__.__name__, result)
        return result


class YConfigAssertions(YPropertyMappedOverrideBase):
    """ Assertions property. Used to define one more assertion. """
    override_keys = ['assertions']
    override_members = [YConfigAssertion]
    override_logical_grouping_type = AssertionsLogicalGrouping

    @property
    def passes(self):
        log.debug("running assertion set")
        try:
            results = []
            stop_executon = False
            for member in self.members:
                for item in member:
                    result = item.result
                    results.append(result)
                    if AssertionsLogicalGrouping.is_exit_condition_met('and',
                                                                       result):
                        stop_executon = True
                        break

                if stop_executon:
                    break

            result = all(results)
        except Exception:
            log.error("exception caught while running assert set:")
            raise

        return result


class YRequirementTypeConfig(YRequirementTypeBase):
    """
    Config requires type property. Provides support for defining a config type
    requirement and perform checks on configuration.
    """
    override_keys = ['config']
    override_autoregister = True

    @property
    def handler(self):
        return self.get_cls(self.content['handler'])

    @property
    def path(self):
        return self.content.get('path')

    @property
    def cfg_handlers(self):
        """
        A config assertion must have a handler and optionally one or more path
        defined.

        If the path(s) are provided and do not exist the assertion returns
        False.

        @return: list of config handlers
        """
        paths = self.path
        if not paths:
            log.debug("no config path provided, creating handler %s "
                      "without args", self.handler)
            return [self.handler()]  # pylint: disable=E1102

        if isinstance(paths, str):
            paths = [paths]

        handlers = []
        for path in paths:
            path = os.path.join(HotSOSConfig.data_root, path)
            if os.path.isfile(path):
                handlers.append(self.handler(path))  # pylint: disable=E1102
                continue

            if os.path.isdir(path):
                path = path + '/*'

            for _path in glob.glob(path):
                if os.path.isfile(_path):
                    handlers.append(self.handler(_path))  # noqa, pylint: disable=E1102

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
                               override_handlers=self.root.override_handlers,
                               resolve_path=self.override_path,
                               context=ctxt)
        for leaf in section.leaf_sections:
            _assertions.append(leaf.assertions.passes)

        return _assertions

    @property
    @intercept_exception
    def _result(self):
        return all(self.assertions)
