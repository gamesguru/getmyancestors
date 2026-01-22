"""Test __main__ functionality."""

import sys
import unittest
from unittest.mock import patch


class TestMain(unittest.TestCase):
    """Test __main__ module."""

    def test_main_module_can_be_imported(self):
        """Test that __main__ module can be imported without error."""
        # Mock getmyanc.app to avoid execution when importing __main__
        with patch("getmyancestors.getmyanc.app"):
            # Mock sys.argv to avoid argument parsing errors
            with patch.object(sys, "argv", ["getmyancestors", "--help"]):
                # Import should work without error
                import getmyancestors.__main__  # pylint: disable=import-outside-toplevel

                self.assertTrue(hasattr(getmyancestors.__main__, "__name__"))

    def test_main_execution_with_mock(self):
        """Test that importing __main__ triggers getmyanc.main() call."""
        # pylint: disable=import-outside-toplevel
        import runpy

        # Create a mock for getmyanc.app
        with patch("getmyancestors.getmyanc.app") as mock_app:
            # Mock sys.argv
            with patch.object(sys, "argv", ["getmyancestors", "--help"]):
                # pylint: disable=import-outside-toplevel,no-name-in-module
                runpy.run_module("getmyancestors.__main__", run_name="__main__")

                self.assertTrue(mock_app.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
