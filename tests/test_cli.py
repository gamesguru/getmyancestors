import pytest
import sys
from unittest.mock import patch, MagicMock
from getmyancestors.getmyancestors import main

class TestCLI:

    @patch('getmyancestors.getmyancestors.Session')
    @patch('getmyancestors.getmyancestors.Tree')
    def test_basic_args(self, MockTree, MockSession):
        """Test that arguments are parsed and passed to classes correctly"""

        # Mock sys.argv to simulate command line execution
        test_args = [
            "getmyancestors",
            "-u", "myuser",
            "-p", "mypass",
            "-i", "KW7V-Y32",
            "--verbose"
        ]

        # Setup the session to appear logged in
        MockSession.return_value.logged = True

        with patch.object(sys, 'argv', test_args):
            main()

        # Verify Session was initialized with CLI args
        MockSession.assert_called_with(
            "myuser",
            "mypass",
            None, # client_id (default)
            None, # redirect_uri (default)
            True, # verbose
            False, # logfile
            60 # timeout
        )

        # Verify Tree started
        MockTree.return_value.add_indis.assert_called_with(["KW7V-Y32"])

    def test_arg_validation(self):
        """Test that invalid ID formats cause an exit"""
        test_args = ["getmyancestors", "-u", "u", "-p", "p", "-i", "BAD_ID"]

        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                # This should trigger sys.exit("Invalid FamilySearch ID...")
                main()
