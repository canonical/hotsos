"""Unit tests for :mod:`cos.cli` scaffold."""

import unittest
from contextlib import redirect_stdout
from io import StringIO

from cos import cli


class TestCliScaffold(unittest.TestCase):
    """Unit tests for the scaffold CLI."""

    def test_main_returns_success(self):
        """Test that the main function returns a success code and prints
        the expected message."""

        out = StringIO()
        with redirect_stdout(out):
            rc = cli.main([])

        self.assertEqual(rc, 0)
        self.assertIn("implementation pending", out.getvalue())

    def test_help_is_available(self):
        """Test that the help option is available and triggers a SystemExit."""

        with self.assertRaises(SystemExit):
            cli.main(["--help"])


if __name__ == "__main__":
    unittest.main()
