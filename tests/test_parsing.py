import pytest
from unittest.mock import MagicMock
from getmyancestors.classes.tree import Tree, Indi, Fam

class TestDataParsing:

    def test_individual_parsing(self, mock_session, sample_person_json):
        """
        Verify that raw JSON from FamilySearch is correctly parsed into an Indi object.
        """
        # Setup the mock to return our sample JSON when get_url is called
        mock_session.get_url = MagicMock(return_value=sample_person_json)

        tree = Tree(mock_session)

        # Act: Add the individual
        tree.add_indis(["KW7V-Y32"])

        # Assert: Check if the individual exists in the tree
        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]

        # Assert: Check attributes
        assert person.name == "John Doe"
        assert person.sex == "M"
        assert person.fid == "KW7V-Y32"

        # Check if Birth fact was parsed (this tests your Fact class logic implicitly)
        birth_fact = next((f for f in person.facts if f.tag == "BIRT"), None)
        assert birth_fact is not None
        assert birth_fact.date == "1 Jan 1900"
        assert birth_fact.place == "New York"

    def test_family_linking(self, mock_session):
        """
        Verify that ensure_family links husband and wife correctly.
        """
        tree = Tree(mock_session)

        # Create dummy individuals
        husb = Indi("HUSB01", tree)
        wife = Indi("WIFE01", tree)

        # Create family
        fam = tree.ensure_family(husb, wife)

        # Assertions
        assert fam.husband == husb
        assert fam.wife == wife

        # Check that the individuals know about the family
        assert fam in husb.fams
        assert fam in wife.fams

        # Ensure creating the same family again returns the same object
        fam2 = tree.ensure_family(husb, wife)
        assert fam is fam2
