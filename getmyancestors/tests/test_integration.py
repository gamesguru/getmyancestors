import json
import os
import traceback
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import requests
from requests.models import PreparedRequest, Response
from typer.testing import CliRunner

from getmyancestors import getmyanc as getmyancestors

runner = CliRunner()


class TestFullIntegration(unittest.TestCase):
    @patch.dict(
        os.environ, {"GMA_I_RESPECT_FAMILYSEARCH_PLEASE_SUPPRESS_LICENSE_PROMPT": "1"}
    )
    @patch("getmyancestors.classes.session.LimiterAdapter")
    # @patch("builtins.print")
    @patch(
        "getmyancestors.classes.session.GMASession.login", autospec=True
    )  # Mock login to prevent network calls
    @patch(
        "getmyancestors.classes.session.GMASession.logged", new_callable=PropertyMock
    )
    @patch("requests.Session.get")
    @patch("requests.Session.post")
    def test_main_execution(
        self,
        mock_post,
        mock_get,
        mock_logged,
        mock_login,
        # mock_print,
        mock_adapter,
    ):
        """
        Integration test for the main execution flow.
        Bypasses login logic and mocks network responses with static data.
        """
        # Suppress unused argument warnings
        _ = (mock_adapter,)

        # Setup mocks
        mock_logged.return_value = True

        # Define a fake login that sets FID directly without network call
        def fake_login(self):
            self.fid = "TEST-123"
            self.lang = "en"
            # Set cookie/header so the 'logged' property returns True
            # Set cookie/header so the 'logged' property returns True
            self.cookies["fssessionid"] = "mock_session_id"

        mock_login.side_effect = fake_login

        # Setup generic response for any GET request
        # users/current -> sets lang='en'
        generic_json = {
            "users": [
                {
                    "personId": "TEST-123",
                    "preferredLanguage": "en",
                    "displayName": "Integrator",
                }
            ],
            "persons": [
                {
                    "id": "TEST-123",
                    "living": True,
                    "names": [
                        {
                            "preferred": True,
                            "type": "http://gedcomx.org/BirthName",
                            "nameForms": [
                                {
                                    "fullText": "Test Person",
                                    "parts": [
                                        {
                                            "type": "http://gedcomx.org/Given",
                                            "value": "Test",
                                        },
                                        {
                                            "type": "http://gedcomx.org/Surname",
                                            "value": "Person",
                                        },
                                    ],
                                }
                            ],
                            "attribution": {"changeMessage": "Automated update"},
                        }
                    ],
                    "notes": [],  # Added notes list for get_notes()
                    "facts": [],
                    "display": {
                        "name": "Test Person",
                        "gender": "Male",
                        "lifespan": "1900-2000",
                    },
                }
            ],
            "childAndParentsRelationships": [],
            "parentAndChildRelationships": [],
        }

        mock_response = Response()
        mock_response.status_code = 200
        mock_response.url = "https://api.familysearch.org/test"
        mock_response.headers = requests.structures.CaseInsensitiveDict(
            {"Content-Type": "application/json"}
        )
        # pylint: disable=protected-access
        mock_response._content = json.dumps(generic_json).encode("utf-8")
        # mock_response.headers is already a CaseInsensitiveDict by default in Response()

        # requests_cache needs response.request to be set
        mock_req = PreparedRequest()
        mock_req.url = "https://api.familysearch.org/test"
        mock_req.method = "GET"
        mock_req.headers = requests.structures.CaseInsensitiveDict({})
        # mock_req.cookies = {} # PreparedRequest doesn't have public cookies dict usually, avoiding access
        mock_response.request = mock_req

        # requests_cache needs response.raw (urllib3 response)
        # It accesses ._request_url
        mock_response.raw = MagicMock()
        # pylint: disable=protected-access
        mock_response.raw._request_url = "https://api.familysearch.org/test"

        # Configure LimiterAdapter mock to return our response
        mock_adapter_instance = mock_adapter.return_value
        mock_adapter_instance.send.return_value = mock_response

        # When Session.get is called, it returns our mock response
        def side_effect_get(url, *args, **kwargs):  # pylint: disable=unused-argument
            # print(f"DEBUG: Mock GET called for {url}")
            return mock_response

        mock_get.side_effect = side_effect_get
        mock_post.return_value = mock_response

        # Output file path in .tmp directory
        output_file = os.path.abspath(".tmp/test_output.ged")
        settings_file = os.path.abspath(".tmp/test_output.settings")

        # Create the .tmp directory if it doesn't exist
        tmp_dir = os.path.dirname(output_file)
        os.makedirs(tmp_dir, exist_ok=True)

        # Prepare arguments mimicking CLI usage (Typer args, no program name)
        test_args = [
            "-u",
            "testuser",
            "-p",
            "testpass",
            "--no-cache",
            "--outfile",
            output_file,
        ]

        # Invoke via CliRunner
        # Note: we invoke getmyancestors.app
        result = runner.invoke(getmyancestors.app, test_args)

        if result.exit_code != 0:
            print(f"STDOUT: {result.stdout}")
            if result.exc_info:
                traceback.print_exception(*result.exc_info)
            self.fail(f"App exited with code {result.exit_code}")

        # Basic assertions
        self.assertTrue(mock_login.called, "Login should have been called")
        self.assertTrue(mock_get.called, "Should have attempted network calls")

        self.assertTrue(
            os.path.exists(output_file),
            f"Output file should have been created at {output_file}",
        )

        if os.path.exists(output_file):
            self.addCleanup(os.remove, output_file)
        if os.path.exists(settings_file):
            self.addCleanup(os.remove, settings_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
