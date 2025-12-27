from unittest.mock import MagicMock, patch

import pytest

from getmyancestors.classes.tree import Indi, Tree


class TestTree:

    @pytest.fixture
    def mock_session(self, mock_user_data):
        session = MagicMock()
        session.fid = "KW7V-Y32"
        session.get_url.return_value = mock_user_data
        session._ = lambda s: s  # Mock translation identity function
        return session

    def test_add_indis(self, mock_session, mock_person_data):
        """Test adding a list of individuals to the tree."""
        tree = Tree(mock_session)

        # Mock the API call for person details
        mock_session.get_url.side_effect = [
            mock_person_data,  # For person details
            None,  # For child relationships (empty for this test)
        ]

        tree.add_indis(["KW7V-Y32"])

        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]
        assert person.name == "John Doe"
        assert person.sex == "M"

    def test_add_parents(self, mock_session):
        """Test fetching parents creates family links."""
        tree = Tree(mock_session)
        child_id = "KW7V-CHILD"
        father_id = "KW7V-DAD"
        mother_id = "KW7V-MOM"

        # Seed child in tree
        tree.indi[child_id] = Indi(child_id, tree)

        # Mock parent relationship response
        mock_session.get_url.return_value = {
            "childAndParentsRelationships": [
                {
                    "father": {"resourceId": father_id},
                    "mother": {"resourceId": mother_id},
                    "fatherFacts": [{"type": "http://gedcomx.org/BiologicalParent"}],
                    "motherFacts": [{"type": "http://gedcomx.org/BiologicalParent"}],
                }
            ]
        }

        # Mock fetching the actual parent person objects
        # We patch add_indis to avoid the recursive fetch details logic for this unit test
        with patch.object(tree, "add_indis") as mock_add_indis:
            result = tree.add_parents({child_id})

            assert father_id in result
            assert mother_id in result

            # Verify family object creation
            fam_key = (tree.indi[father_id], tree.indi[mother_id])
            assert fam_key in tree.fam
            assert tree.indi[child_id] in tree.fam[fam_key].children
