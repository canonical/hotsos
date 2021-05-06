import unittest


from common import utils


class TestSuppress(unittest.TestCase):
    def test_suppress(self):
        @utils.suppress(ValueError)
        def foo():
            raise ValueError("error")

        @utils.suppress(ValueError)
        def bar():
            raise IndexError("error")

        self.assertEqual(foo(), None)
        self.assertRaises(IndexError, bar)
