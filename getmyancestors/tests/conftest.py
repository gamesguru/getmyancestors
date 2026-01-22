import os
from unittest.mock import MagicMock, patch

import pytest

from getmyancestors.classes.session import Session


@pytest.fixture
def mock_session():
    """
    Creates a Session object where the network layer is mocked out.
    """
    with patch("getmyancestors.classes.session.Session.login"):
        session = Session("test_user", "test_pass", verbose=False)

        # Mock cookies
        session.cookies.update({"fssessionid": "mock_session_id", "XSRF-TOKEN": "mock_token"})  # type: ignore

        # Mock session attributes required by Tree
        session.lang = "en"  # type: ignore
        session.fid = "KW7V-Y32"  # type: ignore

        # Mock the network methods
        session.get = MagicMock()  # type: ignore
        session.post = MagicMock()  # type: ignore
        session.get_url = MagicMock()  # type: ignore

        # Mock the translation method
        session._ = lambda s: s  # type: ignore

        yield session


@pytest.fixture
def sample_person_json():
    return {
        "persons": [
            {
                "id": "KW7V-Y32",
                "living": False,
                "display": {
                    "name": "John Doe",
                    "gender": "Male",
                    "lifespan": "1900-1980",
                },
                "facts": [
                    {
                        "type": "http://gedcomx.org/Birth",
                        "date": {"original": "1 Jan 1900"},
                        "place": {"original": "New York"},
                        "attribution": {"changeMessage": "Initial import"},
                    }
                ],
                "names": [
                    {
                        "nameForms": [{"fullText": "John Doe"}],
                        "preferred": True,
                        "type": "http://gedcomx.org/BirthName",
                        "attribution": {"changeMessage": "Initial import"},
                    }
                ],
                "attribution": {"changeMessage": "Initial import"},
            }
        ]
    }


@pytest.fixture
def mock_user_data():
    return {
        "users": [
            {
                "personId": "KW7V-Y32",
                "preferredLanguage": "en",
                "displayName": "Test User",
            }
        ]
    }


@pytest.fixture(autouse=True)
def suppress_license_prompt():
    """Automatically suppress license prompt for all tests"""
    with patch.dict(
        os.environ, {"GMA_I_RESPECT_FAMILYSEARCH_PLEASE_SUPPRESS_LICENSE_PROMPT": "1"}
    ):
        yield
