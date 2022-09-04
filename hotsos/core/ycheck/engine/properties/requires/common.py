import abc
import operator

from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import YPropertyOverrideBase


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

    def apply_op(self, op, input=None, expected=None, force_expected=False):
        """
        @param expected: can be a value or variable name that needs to be
                         resolved. Variable names are identified by having a
                         "$" prefix.
        """
        log.debug("op=%s, input=%s, expected=%s, force_expected=%s", op,
                  input, expected, force_expected)
        if expected is not None:
            if type(expected) == str and expected.startswith("$"):
                varname = expected.partition("$")[2]
                varval = self.context.vars.resolve(varname)
                expected = varval

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

                if expected is not None and normalise_value_types:
                    input = type(expected)(input)

            input = self.apply_op(op[0], input=input, expected=expected,
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
