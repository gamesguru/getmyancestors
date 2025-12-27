import pytest
from unittest.mock import MagicMock, patch
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

        # 3. Setup POST responses (2 calls)
        # Call 1: Login with creds -> returns redirectUrl
        mock_response_login = MagicMock()
        mock_response_login.json.return_value = {"redirectUrl": "http://auth.url"}

        # Call 2: Exchange code for token -> returns access_token
        mock_response_token = MagicMock()
        mock_response_token.json.return_value = {"access_token": "fake_token"}

        session.post = MagicMock(side_effect=[mock_response_login, mock_response_token])

        # 4. Setup GET responses (3 calls)
        # Call 1: Initial page load (sets cookie)
        mock_response_initial = MagicMock()
        mock_response_initial.status_code = 200

        # Call 2: Follow the 'redirectUrl' from the POST above
        mock_response_redirect = MagicMock()
        mock_response_redirect.status_code = 200

        # Call 3: The Authorization endpoint -> returns Location header with code
        mock_response_authorize = MagicMock()
        mock_response_authorize.url = "http://callback?code=123"
        mock_response_authorize.headers = {"location": "http://callback?code=123"}
        mock_response_authorize.status_code = 200 # Often 302, but requests follows it.
        # Note: If allow_redirects=False is used in code, status might be 302.
        # The session.py code checks 'location' in headers regardless.

        session.get = MagicMock(side_effect=[
            mock_response_initial,
            mock_response_redirect,
            mock_response_authorize
        ])

        # 5. Run login
        session.login()

        # 6. Assertions
        assert session.headers.get("Authorization") == "Bearer fake_token"

    def test_get_url_403_ordinances(self):
        """Test handling of 403 Forbidden specifically for ordinances."""
        with patch("getmyancestors.classes.session.Session.login"):
            session = Session("u", "p")
            session.lang = "en"

        response_403 = MagicMock(status_code=403)
        response_403.json.return_value = {"errors": [{"message": "Unable to get ordinances."}]}
        response_403.raise_for_status.side_effect = HTTPError("403 Client Error")

        session.get = MagicMock(return_value=response_403)
        session._ = lambda x: x

        result = session.get_url("/test-ordinances")
        assert result == "error"
