from unittest.mock import MagicMock

import pytest

from getmyancestors.classes.tree import Fam, Indi, Tree


class TestDataParsing:

    def test_individual_parsing(self, mock_session, sample_person_json):
        """
        Verify that raw JSON from FamilySearch is correctly parsed into an Indi object.
        """

        def get_url_side_effect(url, headers=None):
            # Return person data for the main profile
            if url == "/platform/tree/persons/KW7V-Y32":
                return sample_person_json
            # Return None (simulating 204 No Content or empty) for relations
            # to prevent the parser from crashing on missing keys
            return None

        mock_session.get_url.side_effect = get_url_side_effect

        tree = Tree(mock_session)

        # Act
        tree.add_indis(["KW7V-Y32"])

        # Assert
        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]
        assert person.name == "John Doe"
        assert person.sex == "M"

    def test_family_linking(self, mock_session):
        """
        Verify that ensure_family links husband and wife correctly.
        """
        tree = Tree(mock_session)

        # Create dummy individuals manually to avoid API calls
        husb = Indi("HUSB01", tree)
        wife = Indi("WIFE01", tree)

        # Create family
        fam = tree.ensure_family(husb, wife)

        # Assertions
        assert fam.husband == husb
        assert fam.wife == wife
        assert fam in husb.fams
        assert fam in wife.fams

        # Singleton check
        fam2 = tree.ensure_family(husb, wife)
        assert fam is fam2
