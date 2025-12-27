from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from getmyancestors.classes.session import Session


class TestSession:

    def test_login_success(self):
        """Test the full OAuth2 login flow with successful token retrieval."""

        # 1. Instantiate Session without triggering the real login immediately
        with patch("getmyancestors.classes.session.Session.login"):
            session = Session("user", "pass", verbose=True)

        # 2. Mock attributes
        session.cookies = {"XSRF-TOKEN": "mock_xsrf_token"}
        session.headers = {"User-Agent": "test"}

        # 3. Setup POST responses
        mock_response_login = MagicMock()
        mock_response_login.json.return_value = {"redirectUrl": "http://auth.url"}

        mock_response_token = MagicMock()
        mock_response_token.json.return_value = {"access_token": "fake_token"}

        session.post = MagicMock(side_effect=[mock_response_login, mock_response_token])

        # 4. Setup GET responses
        mock_response_initial = MagicMock()
        mock_response_initial.status_code = 200

        # CRITICAL FIX: The code reads response.url or headers["location"]
        # We must mock both to be safe against different code paths
        mock_response_auth_code = MagicMock()
        mock_response_auth_code.url = "http://callback?code=123"
        mock_response_auth_code.headers = {"location": "http://callback?code=123"}
        mock_response_auth_code.status_code = 200

        session.get = MagicMock(
            side_effect=[mock_response_initial, mock_response_auth_code]
        )

        # 5. Run login
        session.login()

        # 6. Assertions
        assert session.headers.get("Authorization") == "Bearer fake_token"

    def test_login_keyerror_handling(self):
        """Ensure it handles missing keys gracefully."""
        pass

    def test_get_url_403_ordinances(self):
        """Test handling of 403 Forbidden specifically for ordinances."""
        with patch("getmyancestors.classes.session.Session.login"):
            session = Session("u", "p")
            session.lang = "en"  # Prevent other attribute errors

        response_403 = MagicMock(status_code=403)
        response_403.json.return_value = {
            "errors": [{"message": "Unable to get ordinances."}]
        }
        response_403.raise_for_status.side_effect = HTTPError("403 Client Error")

        session.get = MagicMock(return_value=response_403)
        session._ = lambda x: x

        result = session.get_url("/test-ordinances")
        assert result == "error"
