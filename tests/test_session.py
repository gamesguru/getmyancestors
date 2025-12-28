from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from getmyancestors.classes.session import Session


class TestSession:

    @patch("getmyancestors.classes.session.webbrowser")
    def test_login_success(self, mock_browser):
        """Test the full OAuth2 login flow with successful token retrieval."""

        with patch("getmyancestors.classes.session.Session.login"):
            session = Session("user", "pass", verbose=True)

        session.cookies = {"XSRF-TOKEN": "mock_xsrf_token"}
        session.headers = {"User-Agent": "test"}

        # Mock POST responses
        mock_response_login = MagicMock()
        mock_response_login.json.return_value = {"redirectUrl": "http://auth.url"}

        mock_response_token = MagicMock()
        mock_response_token.json.return_value = {"access_token": "fake_token"}

        session.post = MagicMock(side_effect=[mock_response_login, mock_response_token])

        # Mock GET responses
        mock_response_initial = MagicMock()
        mock_response_initial.status_code = 200
        mock_response_initial.configure_mock(url="https://familysearch.org/login")

        mock_response_redirect = MagicMock()
        mock_response_redirect.status_code = 200
        mock_response_redirect.configure_mock(url="http://auth.url")

        # The authorization response MUST have the code in the query string
        mock_response_authorize = MagicMock()
        mock_response_authorize.status_code = 200
        # We set both url and headers to cover all bases
        mock_response_authorize.configure_mock(url="http://callback?code=123")
        mock_response_authorize.headers = {"location": "http://callback?code=123"}

        session.get = MagicMock(
            side_effect=[
                mock_response_initial,
                mock_response_redirect,
                mock_response_authorize,
            ]
        )

        # Run login
        session.login()

        assert session.headers.get("Authorization") == "Bearer fake_token"
        mock_browser.open.assert_not_called()

    def test_get_url_403_ordinances(self):
        """Test handling of 403 Forbidden specifically for ordinances."""
        with patch("getmyancestors.classes.session.Session.login"):
            session = Session("u", "p")
            session.lang = "en"

        response_403 = MagicMock(status_code=403)
        response_403.json.return_value = {
            "errors": [{"message": "Unable to get ordinances."}]
        }
        response_403.raise_for_status.side_effect = HTTPError("403 Client Error")

        session.get = MagicMock(return_value=response_403)
        session._ = lambda x: x

        result = session.get_url("/test-ordinances")
        assert result == "error"
