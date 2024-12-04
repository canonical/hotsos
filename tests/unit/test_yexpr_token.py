from unittest import mock

from hotsos.core.ycheck.engine.properties.requires.types.expr import (
    YExprToken,
    YExprNotFound,
    YExprLogicalOpBase,
    YExprLogicalAnd,
    YExprLogicalOr,
    YExprLogicalNot,
    YExprFnLen,
    YExprFnNot,
    YExprFnFile,
    YExprFnSystemd,
    YExprFnReadIni,
    YExprFnReadCert,
    YExprArgBoolean,
    YExprArgNone,
    YExprArgStringLiteral,
    YExprArgInteger,
    YExprArgFloat,
    YExprArgRuntimeVariable,
    YExprSignOp,
    YExprPowerOp,
    YExprMulDivOp,
    YExprAddSubOp,
    YExprComparisonOp,
)
from hotsos.core.exceptions import (
    NotEnoughParametersError,
    TooManyParametersError
)

from . import utils

# ___________________________________________________________________________ #


class MockToken(YExprToken):
    """Mock token for testing."""
    def __init__(self, v):
        super().__init__(None)
        self.v = v

    def eval(self):
        return self.v


class PropertyMock(mock.Mock):
    """Property mock for testing."""

    def __get__(self, obj, obj_type=None):
        return self(obj, obj_type)

# ___________________________________________________________________________ #


class TestYExprToken(utils.BaseTestCase):
    """Unit tests for YExprToken class."""

    def test_operator_operands(self):
        input_v = ("a", "b", "c", "d", "e", "f")
        expected = [("a", "b"), ("c", "d"), ("e", "f")]
        for i, operands in enumerate(YExprToken.operator_operands(input_v)):
            self.assertEqual(operands, expected[i])

    def test_operator_operands_not_even(self):
        input_v = ("a", "b", "c", "d", "e")
        expected = [("a", "b"), ("c", "d")]
        for i, operands in enumerate(YExprToken.operator_operands(input_v)):
            self.assertEqual(operands, expected[i])


# ___________________________________________________________________________ #


class TestYExprNotFound(utils.BaseTestCase):
    """Unit tests for YExprNotFound class."""

    def test_not_found(self):
        obj = YExprNotFound("dummy")
        self.assertEqual(str(obj), "<`dummy` not found>")


# ___________________________________________________________________________ #


class TestYExprLogicalAnd(utils.BaseTestCase):
    """Unit tests for YExprLogicalAnd class."""

    def test_base_default_fn(self):
        self.assertFalse(YExprLogicalOpBase.logical_fn([True]))

    def test_true(self):
        uut = YExprLogicalAnd(
            [[MockToken(True), None, MockToken(True)]]
        )
        self.assertTrue(uut.eval())

    def test_true_multiple(self):
        uut = YExprLogicalAnd(
            [[MockToken(True), None, MockToken(True), None,
              MockToken(True)]]
        )
        self.assertTrue(uut.eval())

    def test_false(self):
        uut = YExprLogicalAnd(
            [[MockToken(True), None, MockToken(False)]]
        )
        self.assertFalse(uut.eval())

    def test_false_multiple(self):
        uut = YExprLogicalAnd(
            [[MockToken(True), None, MockToken(True),
              None, MockToken(False)]]
        )
        self.assertFalse(uut.eval())

    def test_repr(self):
        uut = YExprLogicalAnd(
            [[MockToken(True), None, MockToken(True),
              None, MockToken(False)]]
        )

        self.assertEqual(repr(uut), "True and True and False")


# ___________________________________________________________________________ #


class TestYExprLogicalOr(utils.BaseTestCase):
    """Unit tests for YExprLogicalOr class."""

    def test_true(self):
        uut = YExprLogicalOr(
            [[MockToken(False), None, MockToken(True)]]
        )
        self.assertTrue(uut.eval())

    def test_true_multiple(self):
        uut = YExprLogicalOr(
            [[MockToken(False), None, MockToken(False), None,
              MockToken(True)]]
        )
        self.assertTrue(uut.eval())

    def test_false(self):
        uut = YExprLogicalOr(
            [[MockToken(False), None, MockToken(False)]]
        )
        self.assertFalse(uut.eval())

    def test_false_multiple(self):
        uut = YExprLogicalOr(
            [[MockToken(False), None, MockToken(False),
              None, MockToken(False)]]
        )
        self.assertFalse(uut.eval())

    def test_repr(self):
        uut = YExprLogicalOr(
            [[MockToken(True), None, MockToken(True),
              None, MockToken(False)]]
        )

        self.assertEqual(repr(uut), "True or True or False")


# ___________________________________________________________________________ #

class TestYExprLogicalNot(utils.BaseTestCase):
    """Unit tests for YExprLogicalNot class."""

    def test_true(self):
        uut = YExprLogicalNot(
            [[None, MockToken(False)]]
        )

        self.assertTrue(uut.eval())

    def test_false(self):
        uut = YExprLogicalNot(
            [[None, MockToken(True)]]
        )

        self.assertFalse(uut.eval())

# ___________________________________________________________________________ #


class TestYExprFnLen(utils.BaseTestCase):
    """Unit tests for YExprFnLen class."""

    def test_len_str(self):
        input_v = "This is a string."
        uut = YExprFnLen(
            [None, [MockToken(input_v)]]
        )
        self.assertEqual(uut.eval(), len(input_v))

    def test_len_list(self):
        input_v = ['this', 'is', 'a', 'string.']
        uut = YExprFnLen(
            [None, [MockToken(input_v)]]
        )
        self.assertEqual(uut.eval(), len(input_v))

# ___________________________________________________________________________ #


class TestYExprFnNot(utils.BaseTestCase):
    """Unit tests for YExprFnNot class."""

    def test_true(self):
        uut = YExprFnNot(
            [None, [MockToken(False)]]
        )
        self.assertTrue(uut.eval())

    def test_false(self):
        uut = YExprFnNot(
            [None, [MockToken(True)]]
        )
        self.assertFalse(uut.eval())

# ___________________________________________________________________________ #


class TestYExprFnFile(utils.BaseTestCase):
    """Unit tests for YExprFnFile class."""

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.mtime', new_callable=PropertyMock,
                return_value=42)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.exists', new_callable=PropertyMock,
                return_value=True)
    def test_prop_exists(self, _, mock_property):
        uut = YExprFnFile(
            [None, [MockToken('does_not_matter'), MockToken('mtime')]]
        )
        self.assertEqual(uut.eval(), 42)
        mock_property.assert_called()

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.exists', new_callable=PropertyMock,
                return_value=True)
    def test_exists_noprop(self, _):
        uut = YExprFnFile(
            [None, [MockToken('does_not_matter')]]
        )
        self.assertEqual(uut.eval(), True)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.exists', new_callable=PropertyMock,
                return_value=True)
    def test_prop_does_not_exists(self, _):
        uut = YExprFnFile(
            [None, [MockToken('does_not_matter'), MockToken('not_exists')]]
        )

        with self.assertRaises(Exception):
            uut.eval()

# ___________________________________________________________________________ #


class TestYExprFnSystemd(utils.BaseTestCase):
    """Unit tests for YExprFnSystemd class."""

    def test_no_arg(self):
        uut = YExprFnSystemd(
            [None, []]
        )
        with self.assertRaises(NotEnoughParametersError):
            uut.eval()

#  ___________________________________________________________________________#

    def test_too_many_arg(self):
        uut = YExprFnSystemd(
            [None, [1, 2, 3]]
        )
        with self.assertRaises(TooManyParametersError):
            uut.eval()

#  ___________________________________________________________________________#

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_service_exists(self, mock_systemd_helper):
        mock_systemd_helper.services = mock.MagicMock()
        mock_systemd_helper.services.get.return_value = object()
        uut = YExprFnSystemd(
            [None, [MockToken('does_not_matter')]]
        )
        self.assertTrue(uut.eval())

#  ___________________________________________________________________________#

    def test_service_does_not_exists(self):
        uut = YExprFnSystemd(
            [None, [MockToken('does_not_matter')]]
        )
        self.assertEqual(str(uut.eval()),
                         str(YExprNotFound('does_not_matter')))

#  ___________________________________________________________________________#

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_service_prop_exists(self, mock_systemd_helper):
        # pylint: disable=duplicate-code
        class DummyMock(mock.MagicMock):
            """ For testing. """

        # Create a mock for the services attribute
        mock_services = DummyMock()
        # Set the return value of get to another mock
        mock_service = DummyMock()
        mock_services.get.return_value = mock_service
        # Set test_prop to a PropertyMock that returns 42
        mock_test_prop = PropertyMock(return_value="this is the value")
        type(mock_service).test_prop = mock_test_prop
        mock_systemd_helper.return_value.services = mock_services
        uut = YExprFnSystemd(
            [None, [MockToken('does_not_matter'), MockToken('test_prop')]]
        )
        self.assertEqual(uut.eval(), "this is the value")

#  ___________________________________________________________________________#

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_service_prop_does_not_exists(self, mock_systemd_helper):
        # Create a mock for the services attribute
        mock_services = mock.MagicMock()
        # Set the return value of get to another mock
        mock_service = object()
        mock_services.get.return_value = mock_service
        mock_systemd_helper.return_value.services = mock_services
        uut = YExprFnSystemd(
            [None, [MockToken('does_not_matter'), MockToken('test_prop')]]
        )
        with self.assertRaises(Exception):
            uut.eval()

#  ___________________________________________________________________________#


class TestYExprFnReadIni(utils.BaseTestCase):
    """Unit tests for YExprFnReadIni class."""

    def test_no_arg(self):
        uut = YExprFnReadIni(
            [None, []]
        )
        with self.assertRaises(NotEnoughParametersError):
            uut.eval()

#  ___________________________________________________________________________#

    def test_too_many_arg(self):
        uut = YExprFnReadIni(
            [None, [1, 2, 3, 4, 5]]
        )
        with self.assertRaises(TooManyParametersError):
            uut.eval()

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=42)
    @mock.patch('builtins.open')
    def test_ini_exists(self, _, __, ___):
        uut = YExprFnReadIni(
            [None, [MockToken("does_not_matter"),
                    MockToken("does_not_matter")]]
        )

        self.assertEqual(uut.eval(), 42)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=False)
    def test_ini_does_not_exists(self, _):
        uut = YExprFnReadIni(
            [None, [MockToken("does_not_matter"),
                    MockToken("does_not_matter")]]
        )
        self.assertTrue(isinstance(uut.eval(), YExprNotFound))

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=None)
    def test_ini_does_not_exists_w_section(self, mock_get, __):
        uut = YExprFnReadIni(
            [None, [MockToken("does_not_matter"),
                    MockToken("does_not_matter"),
                    MockToken("the_section")]]
        )
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            self.assertEqual(uut.eval(), None)
            self.assertIn("cannot parse config file", log.output[0])
        mock_get.assert_called_once_with("does_not_matter",
                                         "the_section",
                                         expand_to_list=False)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=None)
    def test_ini_does_not_exists_default(self, _, __):
        uut = YExprFnReadIni(
            [None, [MockToken("does_not_matter"),
                    MockToken("does_not_matter"),
                    MockToken(None),
                    MockToken("default")]]
        )
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            self.assertEqual(uut.eval(), "default")
            self.assertIn("cannot parse config file", log.output[0])


#  ___________________________________________________________________________#


class TestYExprFnReadCert(utils.BaseTestCase):
    """Unit tests for YExprFnReadCert class."""

    def test_no_arg(self):
        uut = YExprFnReadCert(
            [None, []]
        )
        with self.assertRaises(NotEnoughParametersError):
            uut.eval()

#  ___________________________________________________________________________#

    def test_too_many_arg(self):
        uut = YExprFnReadCert(
            [None, [1, 2, 3]]
        )
        with self.assertRaises(TooManyParametersError):
            uut.eval()

    def test_cert_exists(self):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as mock_file:
            uut = YExprFnReadCert(
                [None, [MockToken("does_not_matter")]])
            self.assertTrue(uut.eval())
            mock_file.assert_called_once()

    def test_cert_does_not_exists(self):
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            mock_file.side_effect = OSError()
            uut = YExprFnReadCert(
                [None, [MockToken("does_not_matter")]])
            with self.assertLogs(logger='hotsos', level='WARNING') as log:
                self.assertTrue(isinstance(uut.eval(), YExprNotFound))
                self.assertIn("Unable to read SSL certificate", log.output[0])
            mock_file.assert_called_once()

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SSLCertificate.expiry_date',
                new_callable=PropertyMock,
                return_value=123456)
    def test_cert_read_prop_exists(self, _):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as mock_file:
            uut = YExprFnReadCert(
                [None, [MockToken("does_not_matter"),
                        MockToken("expiry_date")]])
            self.assertEqual(uut.eval(), 123456)
            mock_file.assert_called_once()

    def test_cert_read_prop_does_not_exists(self):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as mock_file:
            uut = YExprFnReadCert(
                [None, [MockToken("does_not_matter"),
                        MockToken("not_a_prop")]])
            with self.assertRaises(Exception):
                self.assertEqual(uut.eval(), 123456)
            mock_file.assert_called_once()


#  ___________________________________________________________________________#


class TestYExprArgBoolean(utils.BaseTestCase):
    """Unit tests for tYExprArgBoolean class."""

    def test_yexpr_boolean_true(self):
        uut = YExprArgBoolean(["TrUe"])
        self.assertTrue(uut.eval())

    def test_yexpr_boolean_false(self):
        uut = YExprArgBoolean(["fAlSe"])
        self.assertFalse(uut.eval())

    def test_yexpr_boolean_garbage(self):
        uut = YExprArgBoolean(["not-a-boolean"])
        with self.assertRaises(Exception):
            uut.eval()

#  ___________________________________________________________________________#


class TestYExprArgNone(utils.BaseTestCase):
    """Unit tests for YExprArgNone class."""

    def test_yexpr_none(self):
        uut = YExprArgNone(["does-not-matter"])
        self.assertEqual(uut.eval(), None)

#  ___________________________________________________________________________#


class TestYExprStringLiteral(utils.BaseTestCase):
    """Unit tests for YExprArgStringLiteral class."""

    def test_yexpr_string_literal(self):
        uut = YExprArgStringLiteral(["does-not-matter"])
        self.assertEqual(uut.eval(), "does-not-matter")

#  ___________________________________________________________________________#


class TestYExprArgInteger(utils.BaseTestCase):
    """Unit tests for YExprArgInteger class."""

    def test_yexpr_integer_from_int_str(self):
        uut = YExprArgInteger(["1"])
        self.assertEqual(uut.eval(), 1)

    def test_yexpr_integer_not_an_int(self):
        uut = YExprArgInteger(["garbage"])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_integer_not_an_int_float(self):
        uut = YExprArgInteger(["1.1"])
        with self.assertRaises(Exception):
            uut.eval()

#  ___________________________________________________________________________#


class TestYExprArgFloat(utils.BaseTestCase):
    """Unit tests for YExprArgFloat class."""

    def test_yexpr_float_from_int_str(self):
        uut = YExprArgFloat(["1.1"])
        self.assertEqual(uut.eval(), 1.1)

    def test_yexpr_float_not_an_int(self):
        uut = YExprArgFloat(["garbage"])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_float_not_an_int_float(self):
        uut = YExprArgFloat(["1"])
        self.assertEqual(uut.eval(), 1.0)


#  ___________________________________________________________________________#


class TestYExprArgRuntimeVariable(utils.BaseTestCase):
    """Unit tests for YExprArgRuntimeVariable class."""

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=1.1)
    def test_yexpr_runtime_variable_exists(self, _):
        # (mgilor): 'thisx' was 'this' at first, but it triggers
        # a Python easter egg which prints out a poem-like text to the console.
        uut = YExprArgRuntimeVariable(["@thisx.is.a.test"], context=None)
        self.assertEqual(uut.eval(), float(1.1))

    def test_yexpr_runtime_variable_does_not_exist(self):
        uut = YExprArgRuntimeVariable(["@thisx.is.a.test"], context=None)
        with self.assertRaises(Exception):
            with self.assertLogs(logger='hotsos', level='ERROR') as log:
                uut.eval()
                self.assertIn("failed to import class a from thisx.is",
                              log.output[0])

#  ___________________________________________________________________________#


class TestYExprSignOp(utils.BaseTestCase):
    """Unit tests for YExprSignOp class."""

    def test_yexpr_signop_plus_negative(self):
        uut = YExprSignOp([["+", MockToken(-1)]])
        self.assertEqual(uut.eval(), -1)

    def test_yexpr_signop_plus_positive(self):
        uut = YExprSignOp([["+", MockToken(1)]])
        self.assertEqual(uut.eval(), 1)

    def test_yexpr_signop_minus_positive(self):
        uut = YExprSignOp([["-", MockToken(1)]])
        self.assertEqual(uut.eval(), -1)

    def test_yexpr_signop_minus_negative(self):
        uut = YExprSignOp([["-", MockToken(-1)]])
        self.assertEqual(uut.eval(), 1)

#  ___________________________________________________________________________#


class TestYExprPowerOp(utils.BaseTestCase):
    """Unit tests for YExprPowerOp class."""

    def test_yexpr_power_op_non_even_args(self):
        uut = YExprPowerOp([[MockToken(3), "**", MockToken(2), "test"]])
        with self.assertRaises(TooManyParametersError):
            uut.eval()

    def test_yexpr_power_op_positive_positive(self):
        uut = YExprPowerOp([[MockToken(3), "**", MockToken(2)]])
        self.assertEqual(uut.eval(), 9)

    def test_yexpr_power_op_positive_negative(self):
        uut = YExprPowerOp([[MockToken(3), "**", MockToken(-2)]])
        self.assertEqual(round(uut.eval(), 5), 0.11111)

    def test_yexpr_power_op_negative_positive(self):
        uut = YExprPowerOp([[MockToken(-3), "**", MockToken(2)]])
        self.assertEqual(uut.eval(), 9)

    def test_yexpr_power_op_negative_negative(self):
        uut = YExprPowerOp([[MockToken(-3), "**", MockToken(-2)]])
        self.assertEqual(round(uut.eval(), 5), 0.11111)

    def test_yexpr_power_op_chain_multiple(self):
        uut = YExprPowerOp([[MockToken(-3), "**",
                             MockToken(-3), "**", MockToken(2)]])
        self.assertEqual(uut.eval(), -19683)

    def test_yexpr_power_op_not_enough_tokens(self):
        uut = YExprPowerOp([[MockToken(-3), "**"]])
        with self.assertRaises(Exception):
            uut.eval()

#  ___________________________________________________________________________#


class TestYExprMulDivOp(utils.BaseTestCase):
    """Unit tests for YExprMulDivOp class."""

    def test_yexpr_mult_op_positive_positive(self):
        uut = YExprMulDivOp([[MockToken(3), "*", MockToken(2)]])
        self.assertEqual(uut.eval(), 6)

    def test_yexpr_mult_op_positive_negative(self):
        uut = YExprMulDivOp([[MockToken(3), "*", MockToken(-2)]])
        self.assertEqual(uut.eval(), -6)

    def test_yexpr_mult_op_negative_positive(self):
        uut = YExprMulDivOp([[MockToken(-3), "*", MockToken(2)]])
        self.assertEqual(uut.eval(), -6)

    def test_yexpr_mult_op_negative_negative(self):
        uut = YExprMulDivOp([[MockToken(-3), "*", MockToken(-2)]])
        self.assertEqual(uut.eval(), 6)

    def test_yexpr_mult_op_chain_multiple(self):
        uut = YExprMulDivOp([[MockToken(3), "*",
                              MockToken(2), "*", MockToken(2)]])
        self.assertEqual(uut.eval(), 12)

    def test_yexpr_mult_op_int_float(self):
        uut = YExprMulDivOp([[MockToken(3.6), "*",
                              MockToken(2)]])
        self.assertEqual(uut.eval(), 7.2)

    def test_yexpr_mult_not_enough_args(self):
        uut = YExprMulDivOp([[MockToken(3), "*"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_mult_not_odd_num_of_args(self):
        uut = YExprMulDivOp([[MockToken(3), "*", MockToken(3), "*"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_div_op_positive_positive(self):
        uut = YExprMulDivOp([[MockToken(6), "/", MockToken(2)]])
        self.assertEqual(uut.eval(), 3)

    def test_yexpr_div_op_positive_negative(self):
        uut = YExprMulDivOp([[MockToken(6), "/", MockToken(-2)]])
        self.assertEqual(uut.eval(), -3)

    def test_yexpr_div_op_negative_positive(self):
        uut = YExprMulDivOp([[MockToken(-6), "/", MockToken(2)]])
        self.assertEqual(uut.eval(), -3)

    def test_yexpr_div_op_negative_negative(self):
        uut = YExprMulDivOp([[MockToken(-6), "/", MockToken(-2)]])
        self.assertEqual(uut.eval(), 3)

    def test_yexpr_div_op_chain_multiple(self):
        uut = YExprMulDivOp([[MockToken(-12), "/",
                              MockToken(-3), "/", MockToken(2)]])
        self.assertEqual(uut.eval(), 2)

    def test_yexpr_div_not_enough_args(self):
        uut = YExprMulDivOp([[MockToken(3), "/"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_div_not_odd_num_of_args(self):
        uut = YExprMulDivOp([[MockToken(3), "/", MockToken(3), "/"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_muldiv_not_a_valid_op_token(self):
        uut = YExprMulDivOp([[MockToken(3), "f", MockToken(3)]])
        with self.assertRaises(Exception):
            uut.eval()

#  ___________________________________________________________________________#


class TestYExprAddSubOp(utils.BaseTestCase):
    """Unit tests for YExprAddSubOp class."""

    def test_yexpr_unrecognized_op(self):
        uut = YExprAddSubOp([[MockToken(3), "?", MockToken(3)]])
        with self.assertRaisesRegex(NameError, r"Unrecognized operation \?"):
            uut.eval()

    def test_yexpr_add_positive_positive(self):
        uut = YExprAddSubOp([[MockToken(3), "+", MockToken(3)]])
        self.assertEqual(uut.eval(), 6)

    def test_yexpr_add_positive_negative(self):
        uut = YExprAddSubOp([[MockToken(3), "+", MockToken(-3)]])
        self.assertEqual(uut.eval(), 0)

    def test_yexpr_add_negative_positive(self):
        uut = YExprAddSubOp([[MockToken(-3), "+", MockToken(3)]])
        self.assertEqual(uut.eval(), 0)

    def test_yexpr_add_negative_negative(self):
        uut = YExprAddSubOp([[MockToken(-3), "+", MockToken(-3)]])
        self.assertEqual(uut.eval(), -6)

    def test_yexpr_add_chain_multiple(self):
        uut = YExprAddSubOp([[MockToken(-3), "+",
                              MockToken(-3), "+", MockToken(6)]])
        self.assertEqual(uut.eval(), 0)

    def test_yexpr_add_not_enough_args(self):
        uut = YExprAddSubOp([[MockToken(-3), "+"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_add_not_odd_number_of_args(self):
        uut = YExprAddSubOp([[MockToken(-3), "+", MockToken(-3), "+"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_sub_positive_positive(self):
        uut = YExprAddSubOp([[MockToken(3), "-", MockToken(3)]])
        self.assertEqual(uut.eval(), 0)

    def test_yexpr_sub_positive_negative(self):
        uut = YExprAddSubOp([[MockToken(3), "-", MockToken(-3)]])
        self.assertEqual(uut.eval(), 6)

    def test_yexpr_sub_negative_positive(self):
        uut = YExprAddSubOp([[MockToken(-3), "-", MockToken(3)]])
        self.assertEqual(uut.eval(), -6)

    def test_yexpr_sub_negative_negative(self):
        uut = YExprAddSubOp([[MockToken(-3), "-", MockToken(-3)]])
        self.assertEqual(uut.eval(), 0)

    def test_yexpr_sub_chain_multiple(self):
        uut = YExprAddSubOp([[MockToken(-3), "-",
                              MockToken(-3), "+", MockToken(6)]])
        self.assertEqual(uut.eval(), 6)

    def test_yexpr_sub_not_enough_args(self):
        uut = YExprAddSubOp([[MockToken(-3), "-"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_sub_not_odd_number_of_args(self):
        uut = YExprAddSubOp([[MockToken(-3), "-", MockToken(-3), "-"]])
        with self.assertRaises(Exception):
            uut.eval()

    def test_yexpr_addsub_not_a_valid_op_token(self):
        uut = YExprMulDivOp([[MockToken(3), "f", MockToken(3)]])
        with self.assertRaises(Exception):
            uut.eval()


#  ___________________________________________________________________________#


class TestYExprComparisonOp(utils.BaseTestCase):
    """Unit tests for YExprComparisonOp class."""

    def test_yexpr_comp_op_lt_true(self):
        for alt in ["<", "LT"]:
            uut = YExprComparisonOp([[MockToken(3), alt, MockToken(4)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_lt_false(self):
        for alt in ["<", "LT"]:
            uut = YExprComparisonOp([[MockToken(4), alt, MockToken(4)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_lte_true(self):
        for alt in ["<=", "LE"]:
            uut = YExprComparisonOp([[MockToken(4), alt, MockToken(4)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_lte_false(self):
        for alt in ["<=", "LE"]:
            uut = YExprComparisonOp([[MockToken(5), alt, MockToken(4)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_gt_true(self):
        for alt in [">", "GT"]:
            uut = YExprComparisonOp([[MockToken(5), alt, MockToken(4)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_gt_false(self):
        for alt in [">", "GT"]:
            uut = YExprComparisonOp([[MockToken(4), alt, MockToken(4)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_gte_true(self):
        for alt in [">=", "GE"]:
            uut = YExprComparisonOp([[MockToken(4), alt, MockToken(4)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_gte_false(self):
        for alt in [">=", "GE"]:
            uut = YExprComparisonOp([[MockToken(3), alt, MockToken(4)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_ne_true(self):
        for alt in ["!=", "NE", "<>"]:
            uut = YExprComparisonOp([[MockToken(3), alt, MockToken(4)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_ne_false(self):
        for alt in ["!=", "NE", "<>"]:
            uut = YExprComparisonOp([[MockToken(3), alt, MockToken(3)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_eq_true(self):
        for alt in ["==", "EQ"]:
            uut = YExprComparisonOp([[MockToken(3), alt, MockToken(3)]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_eq_false(self):
        for alt in ["==", "EQ"]:
            uut = YExprComparisonOp([[MockToken(4), alt, MockToken(3)]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_in_list_true(self):
        for alt in ["IN"]:
            uut = YExprComparisonOp([[MockToken(3), alt,
                                      MockToken([1, 2, 3])]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_in_list_false(self):
        for alt in ["IN"]:
            uut = YExprComparisonOp([[MockToken(3), alt,
                                      MockToken([1, 2, 4])]])
            self.assertFalse(uut.eval())

    def test_yexpr_comp_op_in_string_true(self):
        for alt in ["IN"]:
            uut = YExprComparisonOp([[MockToken("a"), alt,
                                      MockToken("this is a test")]])
            self.assertTrue(uut.eval())

    def test_yexpr_comp_op_in_string_false(self):
        for alt in ["IN"]:
            uut = YExprComparisonOp([[MockToken("a"), alt,
                                      MockToken("this is b test")]])
            self.assertFalse(uut.eval())
