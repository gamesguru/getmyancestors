import unittest
from unittest.mock import MagicMock, patch

from getmyancestors.classes.constants import FACT_TAGS
from getmyancestors.classes.tree.core import Fam, Indi, Tree


class TestForkFeatures(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session.lang = "en"  # Needed for Tree init
        self.tree = Tree(self.mock_session)
        assert self.tree.fs is not None
        self.tree.fs._ = lambda x: x  # type: ignore # Mock translation

    def _setup_mock_api(self, changelog=None, agent_data=None):
        """Helper to mock API responses"""

        def side_effect(url, _headers=None):
            if "changes" in url:
                return changelog
            if "agents" in url:
                # Naive matching for test simplicity
                return agent_data
            return None

        assert self.tree.fs is not None
        self.tree.fs.get_url = MagicMock(side_effect=side_effect)  # type: ignore

    def test_immigration_tag(self):
        """Verify Immigration tag mapping exists"""
        self.assertIn("http://gedcomx.org/Immigration", FACT_TAGS)
        self.assertEqual(FACT_TAGS["http://gedcomx.org/Immigration"], "IMMI")

    def test_exclude_logic_parents(self):
        """Verify add_parents respects exclude list"""
        # Setup: Main person I1, Parent I2
        i1 = Indi("I1", self.tree)
        self.tree.indi["I1"] = i1

        # Manually populate parents list for I1
        i1.parents = {("I2", "I3")}  # Father, Mother

        # Case 1: No exclude
        self.tree.exclude = []
        with patch.object(self.tree, "add_indis") as mock_add_indis:
            self.tree.add_parents({"I1"})
            # verify add_indis called with {"I2", "I3"}
            args, _ = mock_add_indis.call_args
            self.assertEqual(args[0], {"I2", "I3"})

        # Case 2: Exclude I2
        self.tree.exclude = ["I2"]
        with patch.object(self.tree, "add_indis") as mock_add_indis:
            self.tree.add_parents({"I1"})
            # verify add_indis called with {"I3"} only
            args, _ = mock_add_indis.call_args
            self.assertEqual(args[0], {"I3"})

    def test_exclude_logic_children(self):
        """Verify add_children respects exclude list"""
        # Setup: Main person I1, Child I4
        i1 = Indi("I1", self.tree)
        self.tree.indi["I1"] = i1

        # Manually populate children
        i1.children = {("I1", "I3", "I4"), ("I1", "I3", "I5")}

        # Case 1: No exclude
        self.tree.exclude = []
        with patch.object(self.tree, "add_indis") as mock_add_indis:
            self.tree.add_children({"I1"})
            mock_add_indis.assert_called()
            args, _ = mock_add_indis.call_args
            self.assertTrue("I4" in args[0])
            self.assertTrue("I5" in args[0])

        # Case 2: Exclude I5 (filter out filtered_indis)
        self.tree.exclude = ["I5"]
        with patch.object(self.tree, "add_indis") as mock_add_indis:
            self.tree.add_children({"I1"})
            args, _ = mock_add_indis.call_args
            self.assertTrue("I4" in args[0])
            self.assertFalse("I5" in args[0])

    def test_get_contributors(self):
        """Verify get_contributors fetches and parses agent data"""
        # Setup Indi
        i1 = Indi("I1", self.tree)
        self.tree.indi["I1"] = i1

        # Mock API responses
        # 1. Changelog
        changelog = {
            "entries": [
                {
                    "contributors": [
                        {
                            "name": "AgentName",
                            "uri": "https://www.familysearch.org/agents/123",
                        }
                    ]
                }
            ]
        }
        # 2. Agent Data
        agent_data = {
            "agents": [
                {
                    "names": [{"value": "Real Name"}],
                    "emails": [{"resource": "mailto:test@example.com"}],
                    "phones": [{"resource": "tel:555-1234"}],
                }
            ]
        }

        def side_effect(url, _headers=None):
            if "changes" in url:
                return changelog
            if "agents/123" in url:
                return agent_data
            return None

        assert self.tree.fs is not None
        self.tree.fs.get_url = MagicMock(side_effect=side_effect)  # type: ignore

        # Action
        i1.get_contributors()

        # Verify
        self.assertEqual(len(i1.notes), 1)
        note = list(i1.notes)[0]
        self.assertIn("AgentName", note.text)
        self.assertIn("Real Name", note.text)  # Display name
        self.assertIn("test@example.com", note.text)
        self.assertIn("555-1234", note.text)

    def test_get_contributors_family(self):
        """Verify get_contributors works for Families"""
        fam = Fam(tree=self.tree, num="F1")
        fam.fid = "F1"
        self.tree.fam["F1"] = fam

        changelog = {
            "entries": [
                {
                    "contributors": [
                        {
                            "name": "FamAgent",
                            "uri": "https://www.familysearch.org/agents/456",
                        }
                    ]
                }
            ]
        }
        agent_data = {
            "agents": [{"names": [{"value": "Fam Agent"}], "emails": [], "phones": []}]
        }

        self._setup_mock_api(changelog, agent_data)

        fam.get_contributors()

        self.assertEqual(len(fam.notes), 1)
        note = list(fam.notes)[0]
        self.assertIn("FamAgent", note.text)
        self.assertIn("Fam Agent", note.text)

    def test_get_contributors_duplicates_and_missing(self):
        """Verify duplicate contributors are deduped and missing fields handled"""
        i1 = Indi("I1", self.tree)
        self.tree.indi["I1"] = i1

        # Two entries, same agent
        changelog = {
            "entries": [
                {
                    "contributors": [
                        {
                            "name": "AgentX",
                            "uri": "https://www.familysearch.org/agents/X",
                        }
                    ]
                },
                {
                    "contributors": [
                        {
                            "name": "AgentX",
                            "uri": "https://www.familysearch.org/agents/X",
                        }
                    ]
                },
            ]
        }
        # Agent has no email/phone
        agent_data = {
            "agents": [{"names": [{"value": "Agent X"}], "emails": [], "phones": []}]
        }

        self._setup_mock_api(changelog, agent_data)

        i1.get_contributors()

        note = list(i1.notes)[0]
        # Should only list AgentX once
        self.assertEqual(note.text.count("AgentX"), 1)
        # Should not crash on missing email/phone
