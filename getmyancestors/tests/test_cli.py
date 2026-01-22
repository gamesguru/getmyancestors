import traceback
from unittest.mock import patch

from typer.testing import CliRunner

from getmyancestors.getmyanc import app

runner = CliRunner()


class TestCLI:

    @patch("getmyancestors.getmyanc.Session")
    @patch("getmyancestors.getmyanc.CachedSession")
    @patch("getmyancestors.getmyanc.Tree")
    def test_basic_args(self, mock_tree, mock_cached_session, _mock_session):
        """Test that arguments are parsed and passed to classes correctly"""

        # Typer/Click arguments (no need for program name "getmyancestors" in list)
        test_args = [
            "-u",
            "myuser",
            "-p",
            "mypass",
            "-i",
            "KW7V-Y32",
            "--verbose",
        ]

        # Setup the session to appear logged in
        mock_cached_session.return_value.logged = True

        result = runner.invoke(app, test_args)
        if result.exc_info:
            traceback.print_exception(*result.exc_info)

        # Verify exit code
        assert result.exit_code == 0

        # Verify Session was initialized with CLI args
        mock_cached_session.assert_called_once()
        _args, kwargs = mock_cached_session.call_args
        assert kwargs["username"] == "myuser"
        assert kwargs["password"] == "mypass"
        assert kwargs["verbose"] is True
        assert kwargs["cache_control"] is True

        # Verify Tree started
        # Typer parses "-i KW..." into a list
        mock_tree.return_value.add_indis.assert_called_with(["KW7V-Y32"])

    def test_arg_validation(self):
        """Test that invalid ID formats cause an exit"""
        test_args = ["-u", "u", "-p", "p", "-i", "BAD_ID"]

        result = runner.invoke(app, test_args)
        print("STDOUT:", result.stdout)

        # Should exit with code 1 due to validation error
        assert result.exit_code == 1
        # Click/Typer might print to stdout or stderr depending on context/runner
        output = result.stdout + (result.stderr if result.stderr else "")
        assert "Invalid FamilySearch ID: BAD_ID" in output
