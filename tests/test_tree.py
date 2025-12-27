from unittest.mock import MagicMock, patch

import pytest

from getmyancestors.classes.tree import Indi, Tree


class TestTree:

    def test_add_indis(self, mock_session, sample_person_json):
        """Test adding a list of individuals to the tree."""

        # Setup the side effect to return person data or None
        def get_url_side_effect(url, headers=None):
            if "persons/KW7V-Y32" in url:
                return sample_person_json
            return None

        mock_session.get_url.side_effect = get_url_side_effect

        tree = Tree(mock_session)
        tree.add_indis(["KW7V-Y32"])

        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]
        assert person.name == "John Doe"

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

        # We patch add_indis because we don't want to recursively fetch the parents' full details
        # We just want to test that add_parents parses the relationship JSON correctly
        with patch.object(tree, "add_indis") as mock_add_indis:
            result = tree.add_parents({child_id})

            assert father_id in result
            assert mother_id in result

            # Verify family object creation
            fam_key = (tree.indi[father_id], tree.indi[mother_id])
            assert fam_key in tree.fam
            assert tree.indi[child_id] in tree.fam[fam_key].children
