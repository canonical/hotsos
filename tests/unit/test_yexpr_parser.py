from unittest import mock

from pyparsing import pyparsing_test as ppt
from hotsos.core.ycheck.engine.properties.requires.types.expr import (
    init_parser,
    YExprToken,
    YExprNotFound,
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
    YExprArgBase,
    YExprOperand,
    YExprFnBase,
    YExprSignOp,
    YExprPowerOp,
    YExprMulDivOp,
    YExprAddSubOp,
    YExprComparisonOp,
    YExprInvalidArgumentException
)

from . import utils

# ___________________________________________________________________________ #


class MockToken(YExprToken):
    def __init__(self, v):
        self.v = v

    def eval(self):
        return self.v


class PropertyMock(mock.Mock):

    def __get__(self, obj, obj_type=None):
        return self(obj, obj_type)

# ___________________________________________________________________________ #


class TestYExprToken(utils.BaseTestCase):
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
    def test_not_found(self):
        obj = YExprNotFound("dummy")
        self.assertEqual(str(obj), "<`dummy` not found>")


# ___________________________________________________________________________ #


class TestYExprLogicalAnd(utils.BaseTestCase):
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

# ___________________________________________________________________________ #


class TestYExprLogicalOr(utils.BaseTestCase):
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


# ___________________________________________________________________________ #

class TestYExprLogicalNot(utils.BaseTestCase):
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
    def test_prop_does_not_exists(self, _):
        uut = YExprFnFile(
            [None, [MockToken('does_not_matter'), MockToken('not_exists')]]
        )

        with self.assertRaises(Exception):
            uut.eval()

# ___________________________________________________________________________ #


class TestYExprSystemd(utils.BaseTestCase):

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
        class DummyMock(mock.MagicMock):
            pass
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


class TestYExprBoolean(utils.BaseTestCase):

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


class TestYExprNone(utils.BaseTestCase):
    def test_yexpr_none(self):
        uut = YExprArgNone(["does-not-matter"])
        self.assertEqual(uut.eval(), None)

#  ___________________________________________________________________________#


class TestYExprStringLiteral(utils.BaseTestCase):
    def test_yexpr_string_literal(self):
        uut = YExprArgStringLiteral(["does-not-matter"])
        self.assertEqual(uut.eval(), "does-not-matter")

#  ___________________________________________________________________________#


class TestYExprInteger(utils.BaseTestCase):
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


class TestYExprFloat(utils.BaseTestCase):
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
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=1.1)
    def test_yexpr_runtime_variable_exists(self, _):
        # (mgilor): 'thisx' was 'this' at first, but it triggers
        # a Python easter egg which prints out a poem-like text to the console.
        uut = YExprArgRuntimeVariable(["@thisx.is.a.test"])
        self.assertEqual(uut.eval(), float(1.1))

    def test_yexpr_runtime_variable_does_not_exist(self):
        uut = YExprArgRuntimeVariable(["@thisx.is.a.test"])
        with self.assertRaises(Exception):
            with self.assertLogs(logger='hotsos', level='ERROR') as log:
                uut.eval()
                self.assertIn("failed to import class a from thisx.is",
                              log.output[0])

#  ___________________________________________________________________________#


class TestYExprValue(utils.BaseTestCase):

    def test_yexpr_value_v(self):
        class MockValueType(YExprArgBase):
            def eval(self):
                return 42

        uut = YExprOperand([MockValueType([None])])
        self.assertEqual(uut.eval(), 42)

    def test_yexpr_value_f(self):
        class MockFnType(YExprFnBase):
            def eval(self):
                return 42

        uut = YExprOperand([MockFnType([None])])
        self.assertEqual(uut.eval(), 42)

    def test_yexpr_value_u(self):
        class MockObjectType():
            def eval(self):
                return 42

        uut = YExprOperand([MockObjectType()])
        with self.assertRaises(Exception):
            uut.eval()


#  ___________________________________________________________________________#

class TestYExprSignOp(utils.BaseTestCase):
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

#  ___________________________________________________________________________#


# https://github.com/pyparsing/pyparsing/blob/c5d6bdc925cfb70ce88f08c392b82f1b26aa46f2/tests/test_simple_unit.py#L66

class TestYExprParser(ppt.TestParseResultsAsserts, utils.BaseTestCase):
    parser = init_parser()

    def parse_eval(self, expr_str):
        return self.parser.parse_string(expr_str)[0].eval()

    def expect_true(self, expr_str):
        self.assertTrue(self.parse_eval(expr_str))

    def expect_false(self, expr_str):
        self.assertFalse(self.parse_eval(expr_str))

    def expect_isinstance(self, expr_str, type_x):

        self.assertTrue(isinstance(self.parse_eval(expr_str), type_x))

    def test_expr_garbage(self):
        input_v = ["\ttest", "g@rb@g€", "$!?/"]
        for v in input_v:
            with self.assertRaises(YExprInvalidArgumentException):
                self.parser.parse_string(v)

    def test_and_expr_true(self):
        self.expect_true("TrUe and True and True")

    def test_and_expr_false(self):
        self.expect_false("TrUe and False and True")

    def test_and_expr_arg_is_expr(self):
        self.expect_true("len('aaaa') == 4 and not False")

    def test_and_expr_not_a_bool(self):
        with self.assertRaises(YExprInvalidArgumentException):
            self.expect_false("Frue and Talse")

    def test_or_expr_true(self):
        self.expect_true("False or True")

    def test_or_expr_false(self):
        self.expect_false("False or False")

    def test_or_expr_chain(self):
        self.expect_true("False or False or True or False")

    def test_and_or_chain_2(self):
        self.expect_false("False or True and True and False")

    def test_not(self):
        self.expect_true("not false")
        self.expect_false("not true")
        self.expect_false("not not not true")
        self.expect_true("not None")

    def test_not_expr(self):
        self.expect_false("not len('aaa') == 3")

    def test_not_and_or_precedence(self):
        self.expect_true("not False and True")
        self.expect_true("not False or False")

    def test_fn_len_string_literal(self):
        self.assertEqual(self.parse_eval("len('aaaa')"), 4)

    def test_fn_len_none(self):
        self.assertEqual(self.parse_eval("len(None)"), 0)

    def test_fn_len_int(self):
        with self.assertRaises(TypeError):
            self.parse_eval("len(1)")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=["this", "is", "a", "list"])
    def test_fn_len_property(self, _):
        self.assertEqual(self.parse_eval("len(@dummy_prop)"), 4)

    def test_fn_not(self):
        self.expect_true("False or not(True and False)")

    def test_fn_not_none(self):
        self.expect_true("not(None)")

    def test_fn_not_2(self):
        self.expect_false("False or not((True and False) or (False or True))")

    def test_fn_not_3(self):
        self.expect_true("not(3 == 2)")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.mtime', new_callable=PropertyMock,
                return_value=42)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.exists', new_callable=PropertyMock,
                return_value=True)
    def test_fn_file_prop_exists(self, _, __):
        self.expect_true("file('/etc/dummy', 'mtime') == 42")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.exists', new_callable=PropertyMock,
                return_value=True)
    def test_fn_file_prop_does_not_exist(self, _):
        # Should raise exception
        with self.assertRaises(Exception):
            self.parse_eval("file('/etc/dummy', 'mtime') == 42")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_fn_systemd_service_exists(self, _):
        self.expect_true("systemd('dummy-service')")

    def test_fn_systemd_service_does_not_exist(self):
        self.expect_isinstance("systemd('dummy-service')", YExprNotFound)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_fn_systemd_service_and_property_exists(self, mock_systemd_helper):

        class DummyMock(mock.MagicMock):
            pass
        # Create a mock for the services attribute
        mock_services = DummyMock()
        # Set the return value of get to another mock
        mock_service = DummyMock()
        mock_services.get.return_value = mock_service
        # Set test_prop to a PropertyMock that returns 42
        mock_test_prop = PropertyMock(return_value="this is the value")
        type(mock_service).test_prop = mock_test_prop
        mock_systemd_helper.return_value.services = mock_services
        self.assertEqual(self.parse_eval("systemd('dummy', 'test_prop')"),
                         "this is the value")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_fn_systemd_service_exists_no_prop(self, mock_systemd_helper):
        # Create a mock for the services attribute
        mock_services = mock.MagicMock()
        # Set the return value of get to another mock
        mock_service = object()
        mock_services.get.return_value = mock_service
        mock_systemd_helper.return_value.services = mock_services
        with self.assertRaises(Exception):
            self.parse_eval("systemd('dummy', 'test_prop')")

    def test_fn_read_ini_does_not_exist(self):
        self.expect_isinstance("read_ini('/etc/no-such.ini', 'field')",
                               YExprNotFound)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=42)
    @mock.patch("builtins.open")
    def test_fn_read_ini_read_by_key(self, _, __, ___):
        self.assertEqual(
            self.parse_eval("read_ini('/etc/no-such.ini', 'field')"),
            42)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=56)
    @mock.patch("builtins.open")
    def test_fn_read_ini_read_by_key_section(self, _, __, ___):
        self.assertEqual(
            self.parse_eval("read_ini('/etc/no-such.ini', 'field', 'sec')"),
            56)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.exists', new_callable=PropertyMock,
                return_value=True)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=None)
    @mock.patch("builtins.open")
    def test_fn_read_ini_read_by_key_default(self, _, __, ___):
        self.assertEqual(
            self.parse_eval("read_ini('/etc/no-such.ini', 'field', None, 55)"),
            55)

    def test_fn_read_cert_exists(self):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as _:
            self.expect_true("read_cert('/etc/dummy-cert')")

    def test_fn_read_cert_does_not_exist(self):
        with self.assertLogs(logger='hotsos', level='WARNING') as log:
            self.expect_isinstance("read_cert('/etc/dummy-cert')",
                                   YExprNotFound)
            self.assertIn("Unable to read SSL certificate file"
                          " /etc/dummy-cert: [Errno 2] No such "
                          "file or directory: '/etc/dummy-cert'",
                          log.output[0])

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SSLCertificate.expiry_date',
                new_callable=PropertyMock,
                return_value=123456)
    def test_fn_read_cert_prop(self, _):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as _:
            self.assertEqual(
                self.parse_eval("read_cert('/etc/dummy-cert','expiry_date')"),
                123456)

    def test_fn_read_cert_prop_does_not_exist(self):
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")) as _:
            with self.assertRaises(Exception):
                self.parse_eval("read_cert('/etc/dummy-cert','expiry_date')")

    def test_none(self):
        self.assertEqual(self.parse_eval("None"), None)

    def test_string_literal(self):
        self.assertEqual(self.parse_eval("'string literal'"), 'string literal')

    def test_integer_positive(self):
        self.assertEqual(self.parse_eval("1234"), 1234)

    def test_integer_negative(self):
        self.assertEqual(self.parse_eval("-1234"), -1234)

    def test_float_positive(self):
        self.assertEqual(self.parse_eval("1234.56"), 1234.56)

    def test_float_negative(self):
        self.assertEqual(self.parse_eval("-1234.56"), -1234.56)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=42)
    def test_runtime_variable_exists(self, _):
        self.expect_true("@prop.stuff == 42")

    def test_runtime_variable_does_not_exist(self):
        with self.assertRaises(Exception):
            with self.assertLogs(logger='hotsos', level='ERROR') as log:
                self.assertIn("No module named 'prop'", log.output[0])
                self.expect_true("@prop.stuff == 42")
                self.parse_eval("@prop.stuff.mod.x == 42")

    def test_sign_op_neg(self):
        self.assertEqual(self.parse_eval("-(+1)"), -1)

    def test_sign_op_pos(self):
        self.assertEqual(self.parse_eval("+(-1)"), -1)

    def test_power_op(self):
        self.assertEqual(self.parse_eval("3**3**2"), 19683)

    def test_mul_op(self):
        self.assertEqual(self.parse_eval("5*3"), 15)

    def test_mul_op_2(self):
        self.assertEqual(self.parse_eval("-5*3"), -15)

    def test_div_op(self):
        self.assertEqual(self.parse_eval("10/2"), 5)

    def test_div_op_2(self):
        self.assertEqual(self.parse_eval("-10/2"), -5)

    def test_add_op(self):
        self.assertEqual(self.parse_eval("5+3"), 8)

    def test_add_op_string(self):
        self.assertEqual(self.parse_eval("'aa'+'bb'"), 'aabb')

    def test_add_op_2(self):
        self.assertEqual(self.parse_eval("-5+3"), -2)

    def test_sub_op(self):
        self.assertEqual(self.parse_eval("10-2"), 8)

    def test_sub_op_2(self):
        self.assertEqual(self.parse_eval("1-2"), -1)

    def test_comparison_lt_true(self):
        self.expect_true("-3 < -2")

    def test_comparison_lt_false(self):
        self.expect_false("-3 < -4")

    def test_comparison_lte_true(self):
        self.expect_true("-3 <= -3")

    def test_comparison_lte_false(self):
        self.expect_false("-3 <= -4")

    def test_comparison_gt_true(self):
        self.expect_true("-1 > -2")

    def test_comparison_gt_false(self):
        self.expect_false("-5 > -4")

    def test_comparison_gte_true(self):
        self.expect_true("-1 >= -1")

    def test_comparison_gte_false(self):
        self.expect_false("-5 >= -4")

    def test_comparison_eq_true(self):
        self.expect_true("-1 == (-2+1)")

    def test_comparison_eq_false(self):
        self.expect_false("-5 == -4")

    def test_comparison_ne_true(self):
        self.expect_true("(4+5) != (-2+1)")

    def test_comparison_ne_false(self):
        self.expect_false("(-3-2) != (5+-10)")

    def test_comparison_in_string_true(self):
        self.expect_true("'abcd' in '01234abcdefg'")

    def test_comparison_in_string_false(self):
        self.expect_false("'abd' IN '01234abcdefg'")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=[42, 24])
    def test_comparison_in_prop_true(self, _):
        self.expect_true("24 in @test.prop")

    def test_expr_complex_0(self):
        self.expect_true(
            """not((not True or True and False or True)
            AND NOT(1 > 0) OR len('abcd') > 3 AND
            'ab' in 'bcabdef' and -5 == -4) AND TRUE
            """
        )

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=4)
    def test_complex_expression_1(self, _):
        expr = """len('abc') > 2 and not(@hotsos.module.class.property_1 < 5.5)
                  or 3 * (4 + 4) / 2 == 12"""
        self.expect_true(expr)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value=None)
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.FileObj.mtime', new_callable=PropertyMock,
                return_value=42)
    def test_complex_expression_2(self, _, __, ___):
        expr = """file('path/to/file', 'mtime') == 42
                  and read_ini('config.ini', 'key')
                  or systemd('service')"""
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")):
            self.expect_true(expr)

    def test_complex_expression_3(self):
        self.expect_false(
            """(len('abc') + 5 * 2 ** 3) / (3 - 1) > 10
            and (not(True) or False)""")

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=4)
    def test_complex_expression_4(self, _):
        expr = """@hotsos.module.class.property_1 + 123 == 456
                  or read_cert('cert.pem') and True"""
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")):
            self.expect_true(expr)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value=4)
    def test_complex_expression_5(self, _):
        expr = """not not(len('test') > 3 or @module.class.property != None)
                  or file('/path/to/file')"""
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")):
            self.expect_true(expr)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.YExprArgRuntimeVariable.get_property',
                return_value="aaaaaa")
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.IniConfigBase.get',
                return_value='value')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires'
                '.types.expr.SystemdHelper')
    def test_complex_expression_6(self, mock_systemd_helper, _, __):
        mock_systemd_helper.services = mock.MagicMock()
        mock_systemd_helper.services.get.return_value = None
        expr = """# this is a python style comment
                  len(@hotsos.module.class.property_1) * 3 >= 10 and
                  /* and this is a c-style comment*/
                  systemd('aaa') or
                  # another python comment
                  read_ini('config.ini', 'key') == 'value'"""
        with mock.patch("builtins.open",
                        mock.mock_open(read_data="data")):
            self.expect_true(expr)
