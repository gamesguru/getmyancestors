from unittest.mock import MagicMock

import pytest


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


@pytest.fixture
def mock_person_data():
    return {
        "persons": [
            {
                "id": "KW7V-Y32",
                "display": {
                    "name": "John Doe",
                    "gender": "Male",
                    "lifespan": "1900-1980",
                },
                "facts": [
                    {
                        "type": "http://gedcomx.org/Birth",
                        "date": {"original": "1 Jan 1900"},
                    }
                ],
                "names": [{"nameForms": [{"fullText": "John Doe"}]}],
            }
        ]
    }
