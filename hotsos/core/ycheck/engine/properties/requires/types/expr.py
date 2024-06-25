import os
from abc import abstractmethod
from typing import Callable, Iterable

import pyparsing as pp
from hotsos.core.exceptions import (
    NotEnoughParametersError,
    TooManyParametersError,
    NoSuchPropertyError,
    UnexpectedParameterError,
)
from hotsos.core.ycheck.engine.properties.common import PythonEntityResolver
from hotsos.core.ycheck.engine.properties.requires import (
    intercept_exception,
    YRequirementTypeWithOpsBase,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.filestat import FileObj
from hotsos.core.host_helpers.systemd import SystemdHelper
from hotsos.core.host_helpers.config import IniConfigBase
from hotsos.core.host_helpers.ssl import SSLCertificate

# Inspired from the pyparsing examples:
# https://github.com/pyparsing/pyparsing/blob/master/examples/eval_arith.py
# https://github.com/pyparsing/pyparsing/blob/master/examples/simpleBool.py
# Enables "packrat" parsing, which adds memoizing to the parsing logic.
# pylint: disable-next=no-value-for-parameter
pp.ParserElement.enablePackrat()

# ___________________________________________________________________________ #


class YExprToken:
    """Expression token."""

    def __init__(self, tokens):
        self.tokens = tokens

    def token(self, index):
        return self.tokens[index]

    @abstractmethod
    def eval(self):
        """Inheriting class must implement this."""

    @staticmethod
    def operator_operands(tokenlist):
        """generator to extract operator operands in pairs."""
        it = iter(tokenlist)
        while 1:
            try:
                yield (next(it), next(it))
            except StopIteration:
                break


# ___________________________________________________________________________ #


class YExprNotFound:
    """Type for indicating a thing is not found.
    Allows short-circuiting boolean functions to False,
    e.g. systemd('svc-name', 'start_time_secs') > 123 would evaluate to
    False if there's no such service named `svc-name`."""

    def __init__(self, desc):
        self.desc = desc

    def __repr__(self):
        return f"<`{self.desc}` not found>"


class YExprInvalidArgumentException(pp.ParseFatalException):
    """Exception to raise when a expression parsing error is occured."""

    def __init__(self, s, loc, msg):
        super().__init__(s, loc, f"invalid argument '{msg}'")


# ___________________________________________________________________________ #


class YExprLogicalOpBase(YExprToken):
    """Base class for logical operators."""

    logical_fn: Callable[[Iterable[bool]], bool] = lambda _: False

    def eval(self):
        # Yield odd operands 'True' 'and' 'False' 'and' 'False' 'and' 'True'
        # would yield 'True', 'False', 'False', 'True'
        eval_exprs = (t.eval() for t in self.token(0)[::2])

        return self.logical_fn(eval_exprs)


class YExprLogicalAnd(YExprLogicalOpBase):
    """And operator. Binary. Supports chaining."""

    logical_fn = all

    def __repr__(self):
        return " and ".join([str(t.eval()) for t in self.token(0)[::2]])


class YExprLogicalOr(YExprLogicalOpBase):
    """Or operator. Binary. Supports chaining."""

    logical_fn = any

    def __repr__(self):
        return " or ".join([str(t.eval()) for t in self.token(0)[::2]])


class YExprLogicalNot(YExprToken):
    """Not operator. Unary.)"""

    def eval(self):
        return not self.token(0)[1].eval()


# ___________________________________________________________________________ #


# pylint: disable-next=abstract-method
class YExprFnBase(YExprToken):
    """Common base class for all function implementations."""

    def arg(self, index):
        args = self.tokens[1:][0]
        if not len(args) >= (index + 1):
            return None
        return args[index]


class YExprFnLen(YExprFnBase):
    """len(expr) function implementation."""

    def eval(self):
        v = self.arg(0).eval()
        return len(v) if v else 0


class YExprFnNot(YExprFnBase):
    """not(expr) function implementation."""

    def eval(self):
        return not self.arg(0).eval()


class YExprFnFile(YExprFnBase):
    """fstat(fname, prop[optional]) function implementation."""

    def eval(self):
        file_name = self.arg(0).eval()
        fobj = FileObj(file_name)

        if fobj.exists:
            if not self.arg(1):
                return True
        else:
            return YExprNotFound(f"{file_name}")

        property_name = self.arg(1).eval()

        if hasattr(fobj, property_name):
            return getattr(fobj, property_name)

        raise NoSuchPropertyError(f"Unknown file property {property_name}")


class YExprFnSystemd(YExprFnBase):
    """systemd(unit_name, ...property) function implementation."""

    def eval(self):
        if not self.arg(0):
            raise NotEnoughParametersError(
                "systemd(...) function expects at least one argument."
            )
        if self.arg(2):
            raise TooManyParametersError(
                "systemd(...) function expects at most two arguments."
            )

        service_name = self.arg(0).eval()
        service_obj = SystemdHelper([service_name]).services.get(service_name)

        if service_obj:
            if not self.arg(1):
                return True
        else:
            return YExprNotFound(f"{service_name}")

        property_name = self.arg(1).eval()

        if hasattr(service_obj, property_name):
            return getattr(service_obj, property_name)

        raise NoSuchPropertyError(
            f"systemd service `{service_name}` object "
            f"has no such property {property_name}"
        )


class YExprFnReadIni(YExprFnBase):
    """read_ini funciton implementation."""

    def eval(self):

        if not self.arg(1):
            raise NotEnoughParametersError(
                "read_ini(...) function expects at least two arguments."
            )
        if self.arg(4):
            raise TooManyParametersError(
                "read_ini(...) function expects at most four arguments."
            )

        ini_path = self.arg(0).eval()
        path = os.path.join(HotSOSConfig.data_root, ini_path)
        ini_file = IniConfigBase(path)
        if not ini_file.exists:
            return YExprNotFound(f"{path}")

        key = self.arg(1).eval()
        section = self.arg(2).eval() if self.arg(2) else None
        value = ini_file.get(key, section, expand_to_list=False)

        if self.arg(3) and value is None:
            return self.arg(3).eval()

        return value


class YExprFnReadCert(YExprFnBase):
    """read_cert function implementation."""

    def eval(self):
        if not self.arg(0):
            raise NotEnoughParametersError(
                "cert(...) function expects at least on argument."
            )
        if self.arg(2):
            raise TooManyParametersError(
                "cert(...) function expects at most two arguments."
            )

        cert_path = self.arg(0).eval()
        try:
            cert = SSLCertificate(cert_path)
        except OSError:
            return YExprNotFound(f"{cert_path}")

        # If no property is specified, then return True/False
        # indicating that whether the cert file exist or not.
        if not self.arg(1):
            return cert is not None

        property_name = self.arg(1).eval()

        if hasattr(cert, property_name):
            return getattr(cert, property_name)

        raise NoSuchPropertyError(
            f"certificate `{cert_path}` object has no"
            " such property {property_name}"
        )


# ___________________________________________________________________________ #


class YExprArgBoolean(YExprToken):
    """Boolean argument type. Triggered by True and False
    keywords (case-insensitive)."""

    def eval(self):
        if self.token(0).lower() == "true":
            return True

        if self.token(0).lower() == "false":
            return False

        raise ValueError(f"Non-boolean string: {self.token(0)}")


class YExprArgNone(YExprToken):
    """Boolean argument type. Triggered by None
    keyword (case-insensitive)."""

    def eval(self):
        return None


class YExprArgStringLiteral(YExprToken):
    """String literal 'foo'. Triggered by single quotation mark ''."""

    def eval(self):
        return self.token(0)


class YExprArgInteger(YExprToken):
    """Integer argument type. Triggered by [0-9]+"""

    def eval(self):
        return int(self.token(0))


class YExprArgFloat(YExprToken):
    """Integer argument type. Triggered by [0-9]+.[0-9]+"""

    def eval(self):
        return float(self.token(0))


class YExprArgRuntimeVariable(YExprToken, PythonEntityResolver):
    """Runtime variable argument type. Triggered by '@' symbol followed by
    any non-whitespace character."""

    def __init__(self, tokens, context):
        YExprToken.__init__(self, tokens=tokens)
        PythonEntityResolver.__init__(self, context=context)

    def eval(self):
        # use PythonEntityResolver to retrieve value associated with
        # the given name.
        v = self.get_property(self.token(0)[1:])
        return v


# ___________________________________________________________________________ #


class YExprSignOp(YExprToken):
    "Class to evaluate expressions with a leading + or - sign"

    def __init__(self, tokens):
        super().__init__(tokens)
        self.sign = self.token(0)[0]

    def eval(self):
        mult = {"+": 1, "-": -1}[self.sign]
        return mult * self.token(0)[1].eval()


class YExprPowerOp(YExprToken):
    "Class to evaluate power expressions"

    def eval(self):
        if len(self.token(0)) < 3:
            raise NotEnoughParametersError(
                "Power operation expects at least 3 tokens.")

        if len(self.token(0)) % 2 == 0:
            raise TooManyParametersError(
                "Power requires odd amount of tokens.")

        result = self.token(0)[-1].eval()
        for val in self.token(0)[-3::-2]:
            operand = val.eval()
            result = operand**result
        return result


class YExprMulDivOp(YExprToken):
    "Class to evaluate multiplication and division expressions"

    def eval(self):
        if len(self.token(0)) < 3:
            raise NotEnoughParametersError(
                "Mul/div operation expects at least 3 tokens."
            )

        if len(self.token(0)) % 2 == 0:
            raise TooManyParametersError(
                "Mul/div requires odd amount of tokens.")

        prod = self.token(0)[0].eval()
        for op, val in self.operator_operands(self.token(0)[1:]):
            if op == "*":
                prod *= val.eval()
            elif op == "/":
                prod /= val.eval()
            else:
                raise NameError(f"Unrecognized operation {op}")

        return prod


class YExprAddSubOp(YExprToken):
    "Class to evaluate addition and subtraction expressions"

    def eval(self):
        if len(self.token(0)) < 3:
            raise NotEnoughParametersError(
                "Add/sub operation expects at least 3 tokens."
            )

        if len(self.token(0)) % 2 == 0:
            raise UnexpectedParameterError(
                "Add/sub requires odd amount of tokens.")

        sum_v = self.token(0)[0].eval()
        for op, val in self.operator_operands(self.token(0)[1:]):
            if op == "+":
                sum_v += val.eval()
            elif op == "-":
                sum_v -= val.eval()
            else:
                raise NameError(f"Unrecognized operation {op}")
        return sum_v


class YExprComparisonOp(YExprToken):
    "Class to evaluate comparison expressions"

    ops = {
        "<": lambda lhs, rhs: lhs < rhs,
        "<=": lambda lhs, rhs: lhs <= rhs,
        ">": lambda lhs, rhs: lhs > rhs,
        ">=": lambda lhs, rhs: lhs >= rhs,
        "!=": lambda lhs, rhs: lhs != rhs,
        "==": lambda lhs, rhs: lhs == rhs,
        # pylint: disable=unnecessary-lambda
        "LT": lambda lhs, rhs: YExprComparisonOp.ops["<"](lhs, rhs),
        "LE": lambda lhs, rhs: YExprComparisonOp.ops["<="](lhs, rhs),
        "GT": lambda lhs, rhs: YExprComparisonOp.ops[">"](lhs, rhs),
        "GE": lambda lhs, rhs: YExprComparisonOp.ops[">="](lhs, rhs),
        "NE": lambda lhs, rhs: YExprComparisonOp.ops["!="](lhs, rhs),
        "EQ": lambda lhs, rhs: YExprComparisonOp.ops["=="](lhs, rhs),
        "<>": lambda lhs, rhs: YExprComparisonOp.ops["!="](lhs, rhs),
        # pylint:enable=unnecessary-lambda
        "IN": lambda lhs, rhs: lhs in rhs,
    }

    def eval(self):
        lhs = self.token(0)[0].eval()
        for op, val in self.operator_operands(self.token(0)[1:]):
            op_fn = self.ops[op]
            rhs = val.eval()

            # if either of the operands is not found, return False.
            if any(isinstance(x, YExprNotFound) for x in [lhs, rhs]):
                return False

            if not op_fn(lhs, rhs):
                break
            lhs = rhs
        else:
            return True
        return False


# ___________________________________________________________________________ #


def _tok_error(exception_type):
    """Parser matcher type for raising parse errors."""

    def raise_exception(s, loc, typ):
        raise exception_type(s, loc, typ[0])

    return pp.Word(pp.printables).setParseAction(raise_exception)


def _tok_boolean_kw():
    # Define True & False as their corresponding bool values
    # Example: [True, False, TRUE, FALSE, TrUe, FaLsE]
    kw = pp.CaselessKeyword("True") | pp.CaselessKeyword("False")
    kw.setParseAction(lambda s, loc, tokens: YExprArgBoolean(tokens))
    return kw


def _tok_none_kw():
    # Define `None` as keyword for None
    kw = pp.CaselessKeyword("None")
    kw.setParseAction(lambda s, loc, tokens: YExprArgNone(tokens))
    return kw


def _tok_string_literal():
    # Declare syntax for string literals
    # Example: ['this is a test']
    kw = pp.QuotedString("'")
    kw.setParseAction(lambda s, loc, tokens: YExprArgStringLiteral(tokens))
    return kw


def _tok_integer():
    # Declare syntax for integers
    # example: [123, 1, 1234]
    kw = pp.Word(pp.nums)
    kw.setParseAction(lambda s, loc, tokens: YExprArgInteger(tokens))
    return kw


def _tok_real():
    # Declare syntax for real numbers (float)
    # example. [1.3, 1.23]
    kw = pp.Combine(pp.Word(pp.nums) + "." + pp.Word(pp.nums))
    kw.setParseAction(lambda s, loc, tokens: YExprArgFloat(tokens))
    return kw


def _tok_python_property(context):
    # Declare syntax for Python runtime properties.
    # Properties start with `@` symbol and can contain alphanumeric + '.', '_'`
    # example. [@hotsos.module.class.property_1]
    kw = pp.Combine("@" + pp.Word(pp.alphanums + "._-:/"))
    kw.setParseAction(
        lambda s, loc, tokens: YExprArgRuntimeVariable(tokens, context))
    return kw


def _make_fn_token(expr, name, parser):
    lpar, rpar = map(pp.Suppress, "()")
    function_call_tail = pp.Group(
        lpar + pp.Optional(pp.delimited_list(expr)) + rpar)
    fn = pp.CaselessKeyword(name) + function_call_tail
    fn.setParseAction(lambda s, loc, tokens: parser(tokens))
    return fn


def _tok_functions(expr):
    return (
        _make_fn_token(expr, "len", YExprFnLen)
        | _make_fn_token(expr, "not", YExprFnNot)
        | _make_fn_token(expr, "file", YExprFnFile)
        | _make_fn_token(expr, "systemd", YExprFnSystemd)
        | _make_fn_token(expr, "read_ini", YExprFnReadIni)
        | _make_fn_token(expr, "read_cert", YExprFnReadCert)
    )


def _tok_arith_expr(base_expr):
    # Declare arithmetic operations
    signop = pp.one_of("+ -")
    multop = pp.one_of("* /")
    plusop = pp.one_of("+ -")
    expop = pp.Literal("**")
    arith_expr = pp.infix_notation(
        base_expr,
        [
            (
                signop,
                1,
                pp.OpAssoc.RIGHT,
                lambda s, loc, tokens: YExprSignOp(tokens),
            ),
            (
                expop,
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprPowerOp(tokens),
            ),
            (
                multop,
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprMulDivOp(tokens),
            ),
            (
                plusop,
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprAddSubOp(tokens),
            ),
        ],
    )
    return arith_expr


def _tok_comp_expr(base_expr):
    # Declare comparison/boolean operations
    comparisonop = pp.one_of(
        " ".join(YExprComparisonOp.ops.keys()), caseless=True)
    comp_expr = pp.infix_notation(
        base_expr,
        [
            (
                comparisonop,
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprComparisonOp(tokens),
            ),
        ],
    )
    return comp_expr


def _tok_logical_expr(base_expr):
    logical_expr = pp.infix_notation(
        base_expr,
        [
            (
                pp.CaselessKeyword("not"),
                1,
                pp.OpAssoc.RIGHT,
                lambda s, loc, tokens: YExprLogicalNot(tokens),
            ),
            (
                pp.CaselessKeyword("and"),
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprLogicalAnd(tokens),
            ),
            (
                pp.CaselessKeyword("or"),
                2,
                pp.OpAssoc.LEFT,
                lambda s, loc, tokens: YExprLogicalOr(tokens),
            ),
        ],
    )
    return logical_expr


def init_parser(context=None):
    """Initialize parser for check expressions.

    The grammar currently supports the following constructs:

    Keywords:
        None, True, False
    built-ins:
        integer, float, string literal
    runtime:
        python properties
    functions:
        len(...)
        not(...)
    arithmetic:
        - sign
        - plus/minus
        - exponent
        - mul/div
    boolean:
        - gt/ge
        - lt/le
        - eq/ne
        - in/and/or/not
    """

    # This is a forward declaration because functions can take an expression as
    # an argument..
    expr = pp.Forward()

    # The order matters.
    keywords = _tok_boolean_kw() | _tok_none_kw()
    constants = _tok_real() | _tok_integer() | _tok_string_literal()
    operand = (
        _tok_functions(expr) | keywords |
        constants | _tok_python_property(context)
    )

    arith_expr = _tok_arith_expr(operand)
    comp_expr = _tok_comp_expr(arith_expr)
    logical_expr = _tok_logical_expr(comp_expr)

    # Append all of them to "expr". Anything that does not match
    # to the comp_expr is an error.
    expr <<= logical_expr | _tok_error(YExprInvalidArgumentException)
    # Ignore comments.
    expr.ignore(pp.python_style_comment)
    expr.ignore(pp.c_style_comment)
    return expr


class YPropertyExpr(YRequirementTypeWithOpsBase):
    """Expression requirement property type."""

    _override_keys = ["expression"]
    _overrride_autoregister = True

    @property
    def input(self):
        return self.content

    @property
    @intercept_exception
    def _result(self):
        parser = init_parser(context=self.context)
        parsed_expr = parser.parse_string(self.input)
        result = parsed_expr[0].eval()
        if isinstance(result, YExprNotFound):
            return False
        return result
