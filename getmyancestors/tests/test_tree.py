import unittest
from unittest.mock import MagicMock, patch

from getmyancestors.classes.tree.core import Tree


class TestTree(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session._ = lambda x: x  # Mock translation function
        self.mock_session.lang = "en"  # Mock language code for babelfish
        self.tree = Tree(self.mock_session)

    def test_tree_init(self):
        """Test tree initialization."""
        self.assertEqual(len(self.tree.indi), 0)
        self.assertEqual(len(self.tree.fam), 0)

    @patch("getmyancestors.classes.session.GMASession.get_url")
    def test_ensure_place_new(self, mock_get_url):
        """Test creating a new place."""
        mock_get_url.return_value = {"id": "123", "names": [{"value": "New Place"}]}
        place = self.tree.ensure_place("New Place")
        self.assertEqual(place.name, "New Place")
        self.assertIn("New Place", self.tree.places_by_names)

    @patch("getmyancestors.classes.session.GMASession.get_url")
    def test_ensure_place_existing(self, _mock_get_url):
        """Test retrieving an existing place."""
        place1 = self.tree.ensure_place("Existing Place")
        place2 = self.tree.ensure_place("Existing Place")
        self.assertEqual(place1, place2)
        self.assertEqual(len(self.tree.places_by_names), 1)
