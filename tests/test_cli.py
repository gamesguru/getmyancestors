import sys
from unittest.mock import MagicMock, patch

import pytest

from getmyancestors.getmyancestors import main


class TestCLI:

    @patch("getmyancestors.getmyancestors.Session")
    @patch("getmyancestors.getmyancestors.Tree")
    @patch(
        "sys.argv",
        ["getmyancestors", "-u", "testuser", "-p", "testpass", "-i", "KW7V-Y32"],
    )
    def test_main_execution(self, mock_tree, mock_session):
        """Test that main runs with basic arguments."""
        mock_fs = mock_session.return_value
        mock_fs.logged = True

        # Run main
        main()

        # Verify Session initialized with args
        mock_session.assert_called_with(
            username="testuser",
            password="testpass",
            client_id=None,
            redirect_uri=None,
            verbose=False,
            logfile=False,
            timeout=60,
        )

        # Verify Tree operations
        mock_tree.return_value.add_indis.assert_called()
        mock_tree.return_value.print.assert_called()

    @patch("getmyancestors.getmyancestors.Session")
    @patch(
        "sys.argv",
        ["getmyancestors", "-u", "testuser", "-p", "testpass", "--descend", "2"],
    )
    def test_descend_argument(self, mock_session):
        """Test that the descend argument is passed to logic."""
        mock_fs = mock_session.return_value
        mock_fs.logged = True

        # We need to mock Tree because main interacts with it deeply
        with patch("getmyancestors.getmyancestors.Tree") as mock_tree:
            mock_tree_instance = mock_tree.return_value
            # Return empty sets to stop loops
            mock_tree_instance.add_children.return_value = set()

            main()

            # Verify add_children was called (logic inside main triggers this based on args.descend)
            assert mock_tree_instance.add_children.called
