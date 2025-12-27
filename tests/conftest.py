import pytest
from unittest.mock import MagicMock
import sys
import os

# Ensure we can import the module from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from getmyancestors.classes.session import Session

@pytest.fixture
def mock_session():
    """
    Creates a Session object where the network layer is mocked out.
    """
    # Create the session but suppress the automatic login() call in __init__
    # We do this by mocking the login method *before* instantiation
    with pytest.helpers.patch_method(Session, 'login'):
        session = Session("test_user", "test_pass", verbose=False)

        # Manually set logged status to True so checks pass
        # We need to mock the cookies since 'logged' property checks for 'fssessionid'
        session.cookies = {"fssessionid": "mock_session_id"}

        # Mock the request methods
        session.get = MagicMock()
        session.post = MagicMock()

        # Mock the internal translation method to just return the string
        session._ = lambda s: s

        return session

@pytest.fixture
def sample_person_json():
    """Returns a raw JSON response representing a Person from FamilySearch"""
    return {
        "persons": [{
            "id": "KW7V-Y32",
            "display": {
                "name": "John Doe",
                "gender": "Male",
                "lifespan": "1900-1980"
            },
            "facts": [
                {
                    "type": "http://gedcomx.org/Birth",
                    "date": {"original": "1 Jan 1900"},
                    "place": {"original": "New York"}
                }
            ],
            "names": [
                {
                    "nameForms": [{"fullText": "John Doe"}]
                }
            ]
        }]
    }

# Helper to patch methods cleanly in fixtures
class Helpers:
    @staticmethod
    def patch_method(cls, method_name):
        from unittest.mock import patch
        return patch.object(cls, method_name)

@pytest.fixture
def helpers():
    return Helpers
