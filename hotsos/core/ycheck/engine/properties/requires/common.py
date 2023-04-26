import abc
import operator

from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import YPropertyOverrideBase
from hotsos.core.utils import cached_property


def intercept_exception(f):
    """
    If a call raises an AttributeError it will first be handled by
    the propertree engine which can produce confusing/misleading logs
    as to the origin of the exception. This can be used to wrap these
    calls so any exception is printed with its original traceback
    before being re-raised.
    """
    def intercept_exception_inner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            log.exception("function %s raised exception:", f.__name__)
            raise

    return intercept_exception_inner


class CheckItemsBase(abc.ABC):
    """
    Provides a standard way for check items to be defined i.e.

    * a single value e.g. str, int
    * a list
    * a dict

    Items are then accessed by iterating over this object and are always
    presented as a tuple(key, value).
    """

    def __init__(self, raw):
        self._items = {}
        if type(raw) == dict:
            self._items = raw
        elif type(raw) == list:
            self._items = {i: None for i in raw}
        else:
            self._items = {raw: None}

    def __iter__(self):
        for item in self._items.items():
            yield item


class PackageCheckItemsBase(CheckItemsBase):

    @cached_property
    def packages_to_check(self):
        return [item[0] for item in self]

    @abc.abstractmethod
    def packaging_helper(self):
        """
        Returns and implementation of host_helpers.packaging.PackageHelperBase
        e.g. APTPackagehelper or SnapPackageHelper.
        """

    @cached_property
    def installed(self):
        _installed = []
        for p in self.packages_to_check:
            if self.packaging_helper.is_installed(p):  # pylint: disable=E1101
                _installed.append(p)

        return _installed

    @cached_property
    def not_installed(self):
        _all = self.packages_to_check
        return set(self.installed).symmetric_difference(_all)


class OpsUtils(object):

    def ops_to_str(self, ops):
        """
        Convert an ops list of tuples to a string. This is typically used when
        printing in a msg or storing in the cache.
        """
        if not ops:
            return ""

        _result = []
        for op in ops:
            item = str(op[0])
            if len(op) > 1:
                if type(op[1]) == str:
                    item = "{} \"{}\"".format(item, op[1])
                else:
                    item = "{} {}".format(item, op[1])

            _result.append(item)

        return ' -> '.join(_result)

    def _apply_op(self, op, input=None, expected=None, force_expected=False):
        """
        @param expected: can be a value or variable name that needs to be
                         resolved. Variable names are identified by having a
                         "$" prefix.
        """
        log.debug("op=%s, input=%s, expected=%s, force_expected=%s", op,
                  input, expected, force_expected)
        try:
            if expected is not None or force_expected:
                return getattr(operator, op)(input, expected)

            return getattr(operator, op)(input)
        except Exception:
            log.exception("failed to apply operator '%s'", op)
            raise

    def apply_ops(self, ops, input=None, normalise_value_types=False):
        """
        Takes a list of operations and processes each one where each takes as
        input the output of the previous.

        @param ops: list of tuples of operations and optional args.
        @param input: the value that is used as input to the first operation.
        @param normalise_value_types: if an operation has an expected value and
                                      and this is True, the type of the input
                                      will be cast to that of the expectced
                                      value.
        """
        log.debug("ops=%s, input=%s", ops, input)
        if type(ops) != list:
            raise Exception("Expected list of ops but got {}".
                            format(ops))

        for op in ops:
            expected = None
            force_expected = False
            if len(op) > 1:
                # if an expected value was provided we must use it regardless
                # of what it is.
                force_expected = True
                expected = op[1]

                if expected is not None:
                    if type(expected) == str and expected.startswith("$"):
                        varname = expected.partition("$")[2]
                        varval = self.context.vars.resolve(varname)  # noqa, pylint: disable=E1101
                        expected = varval

                    if normalise_value_types:
                        log.debug("normalising type(input)=%s to "
                                  "type(expected)=%s", type(input),
                                  type(expected))
                        input = type(expected)(input)

            input = self._apply_op(op[0], input=input, expected=expected,
                                   force_expected=force_expected)

        return input


class YRequirementTypeBase(YPropertyOverrideBase, OpsUtils):

    @abc.abstractproperty
    def _result(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """

    def __call__(self):
        try:
            return self._result
        except Exception:
            # display traceback here before it gets swallowed up.
            log.exception("requires.%s.result raised the following",
                          self.__class__.__name__)
            raise


class YRequirementTypeWithOpsBase(YRequirementTypeBase):

    @property
    def default_ops(self):
        return [['truth']]

    @property
    def ops(self):
        if type(self.content) != dict:
            return self.default_ops

        return self.content.get('ops', self.default_ops)


class ServiceCheckItemsBase(CheckItemsBase):

    @cached_property
    def _started_after_services(self):
        svcs = []
        for _, settings in self:
            if type(settings) != dict:
                continue

            svc = settings.get('started-after')
            if svc:
                svcs.append(svc)

        return svcs

    @cached_property
    def _services_to_check(self):
        return [item[0] for item in self]

    @property
    def _svcs_all(self):
        """
        We include started-after services since if a check has specified one it
        is expected to exist for that check to pass.
        """
        return self._services_to_check + self._started_after_services

    @property
    @abc.abstractmethod
    def _svcs_info(self):
        """ ServiceManagerBase implementation with _svcs_all as input. """

    @cached_property
    def not_installed(self):
        _installed = self.installed.keys()
        return set(_installed).symmetric_difference(self._svcs_all)

    @cached_property
    def installed(self):
        return self._svcs_info.services

    def processes_running(self, processes):
        """ Check any processes provided. """
        a = set(processes)
        b = set(self._svcs_info.processes.keys())
        return a.issubset(b)
