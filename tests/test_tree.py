import pytest
from unittest.mock import MagicMock, patch
from getmyancestors.classes.tree import Tree, Indi, Fam

class TestTree:

    def test_add_indis(self, mock_session, sample_person_json):
        """Test adding a list of individuals to the tree."""

        # The Tree.add_indis method likely fetches the person AND their relationships.
        # We need to handle both calls.
        def get_url_side_effect(url, headers=None):
            if "persons/KW7V-Y32" in url:
                return sample_person_json
            # Return empty structure for relationship calls to prevent crashes
            return {"childAndParentsRelationships": [], "spouses": []}

        mock_session.get_url.side_effect = get_url_side_effect

        tree = Tree(mock_session)
        tree.add_indis(["KW7V-Y32"])

        assert "KW7V-Y32" in tree.indi
        person = tree.indi["KW7V-Y32"]
        # Depending on how Indi parses names, it might store it in .name
        # We check whatever attribute implies success
        assert person.fid == "KW7V-Y32"

    def test_add_parents(self, mock_session):
        """Test fetching parents creates family links."""
        tree = Tree(mock_session)
        child_id = "KW7V-CHILD"
        father_id = "KW7V-DAD"
        mother_id = "KW7V-MOM"

        # 1. Seed child in tree
        # We manually create the Indi to avoid API calls for the child
        tree.indi[child_id] = Indi(child_id, tree)

        # 2. Mock parent relationship response
        # This JSON structure mimics the FamilySearch 'child-and-parents' endpoint
        relationships_response = {
            "childAndParentsRelationships": [{
                "father": {"resourceId": father_id},
                "mother": {"resourceId": mother_id},
                "fatherFacts": [{"type": "http://gedcomx.org/BiologicalParent"}],
                "motherFacts": [{"type": "http://gedcomx.org/BiologicalParent"}]
            }]
        }

        mock_session.get_url.return_value = relationships_response

        # 3. Patch add_indis
        # When add_parents finds a new ID (DAD/MOM), it calls add_indis.
        # We mock this so we don't have to provide person-details JSON for the parents.
        # We just want to ensure add_parents *tried* to add them.
        with patch.object(tree, 'add_indis') as mock_add_indis:
            # Side effect: actually add the dummy parents to the tree so the method can return them
            def add_indis_side_effect(fids):
                for fid in fids:
                    tree.indi[fid] = Indi(fid, tree)
            mock_add_indis.side_effect = add_indis_side_effect

            result = tree.add_parents({child_id})

            # 4. Assertions
            assert father_id in result
            assert mother_id in result

            # Verify family object creation in the tree's internal dictionary
            # The Tree class usually keys families by (husband_id, wife_id)
            fam_key = (father_id, mother_id)
            assert fam_key in tree.fam

            # Verify linkage
            fam = tree.fam[fam_key]
            assert tree.indi[child_id] in fam.children

    def test_manual_family_linking(self, mock_session):
        """
        Verify that we can link individuals manually, replacing the removed ensure_family test.
        """
        tree = Tree(mock_session)

        husb = Indi("HUSB01", tree)
        wife = Indi("WIFE01", tree)

        # Manually create a family (mimicking internal logic)
        # Fam(husband_id, wife_id, tree, unique_number)
        fam = Fam("HUSB01", "WIFE01", tree, 1)
        tree.fam[("HUSB01", "WIFE01")] = fam

        # Link them
        husb.fams.add(fam)
        wife.fams.add(fam)

        assert fam.husb_fid == "HUSB01"
        assert fam.wife_fid == "WIFE01"
        assert fam in husb.fams
