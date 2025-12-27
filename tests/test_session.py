from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from getmyancestors.classes.session import Session


class TestSession:

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_login_success(self, mock_post, mock_get):
        """Test the full OAuth2 login flow with successful token retrieval."""
        # Setup the sequence of responses for the login flow
        mock_get.side_effect = [
            MagicMock(cookies={"XSRF-TOKEN": "abc"}),  # 1. Initial page load
            MagicMock(status_code=200),  # 3. Redirect URL page
            MagicMock(
                headers={"location": "http://callback?code=123"}
            ),  # 4. Auth callback
        ]

        # Mock the JSON response for the login POST
        mock_post.side_effect = [
            MagicMock(json=lambda: {"redirectUrl": "http://auth.url"}),  # 2. Login POST
            MagicMock(json=lambda: {"access_token": "fake_token"}),  # 5. Token POST
        ]

        # Initialize session (triggers login)
        session = Session("user", "pass", verbose=True)

        assert session.logged is True
        assert session.headers["Authorization"] == "Bearer fake_token"

    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_login_failure_bad_creds(self, mock_post, mock_get):
        """Test login failure when credentials are rejected."""
        mock_get.return_value.cookies = {"XSRF-TOKEN": "abc"}

        # Simulate login error response
        mock_post.return_value.json.return_value = {"loginError": "Invalid credentials"}

        session = Session("user", "badpass")

        # Should not have session cookie or auth header
        assert session.logged is False
        assert "Authorization" not in session.headers

    @patch("getmyancestors.classes.session.Session.login")  # Prevent auto-login in init
    def test_get_url_401_retry(self, mock_login):
        """Test that a 401 response triggers a re-login and retry."""
        session = Session("u", "p")

        # Mock Session.get directly on the instance to control responses
        with patch.object(session, "get") as mock_request_get:
            # First call 401, Second call 200 OK
            mock_request_get.side_effect = [
                MagicMock(status_code=401),
                MagicMock(status_code=200, json=lambda: {"data": "success"}),
            ]

            result = session.get_url("/test-endpoint")

            assert mock_login.call_count == 2  # Once init, Once after 401
            assert result == {"data": "success"}

    @patch("getmyancestors.classes.session.Session.login")
    def test_get_url_403_ordinances(self, mock_login):
        """Test handling of 403 Forbidden specifically for ordinances."""
        session = Session("u", "p")

        with patch.object(session, "get") as mock_request_get:
            response_403 = MagicMock(status_code=403)
            response_403.json.return_value = {
                "errors": [{"message": "Unable to get ordinances."}]
            }
            response_403.raise_for_status.side_effect = HTTPError("403 Client Error")

            mock_request_get.return_value = response_403

            result = session.get_url("/test-ordinances")

            assert result == "error"
