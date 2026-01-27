"""Test merge idempotency - ensure re-merging produces no duplicates."""

import io
import os
import shutil
import tempfile
import unittest

from getmyancestors.classes.gedcom import Gedcom
from getmyancestors.classes.tree import Fam, Indi, Tree


class TestMergeIdempotency(unittest.TestCase):
    """Test that merging is idempotent - merging A+B then (A+B)+A should equal A+B."""

    def setUp(self):
        """Create sample GEDCOM content for testing."""
        # Simple GEDCOM with one individual (simulating FamilySearch output)
        self.gedcom_a = """0 HEAD
1 SOUR getmyancestors
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
1 _FSFTID AAAA-111
1 BIRT
2 DATE 1 JAN 1900
2 PLAC New York, USA
1 NOTE This is a test note
0 @F1@ FAM
1 HUSB @I1@
1 _FSFTID FFFF-111
0 TRLR
"""

        # Different GEDCOM with different individual
        self.gedcom_b = """0 HEAD
1 SOUR getmyancestors
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I2@ INDI
1 NAME Jane /Smith/
1 SEX F
1 _FSFTID BBBB-222
1 BIRT
2 DATE 15 MAR 1905
2 PLAC Boston, USA
0 @F2@ FAM
1 WIFE @I2@
1 _FSFTID FFFF-222
0 TRLR
"""

        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)

        self.file_a = os.path.join(self.temp_dir, "a.ged")
        self.file_b = os.path.join(self.temp_dir, "b.ged")
        with open(self.file_a, "w", encoding="utf-8") as f:
            f.write(self.gedcom_a)
        with open(self.file_b, "w", encoding="utf-8") as f:
            f.write(self.gedcom_b)

    def _count_data_lines(self, tree: Tree) -> int:
        """Count output lines."""
        output = io.StringIO()
        tree.print(output)
        lines = output.getvalue().strip().split("\n")
        return len(lines)

    def _merge_files(self, *files) -> Tree:
        """Merge multiple GEDCOM files into a single tree."""
        contents = []
        for fpath in files:
            with open(fpath, "r", encoding="utf-8") as f:
                contents.append(f.read())
        return self._merge_gedcoms(*contents)

    def _merge_gedcoms(self, *gedcom_strings) -> Tree:
        """Merge multiple GEDCOM strings into a single tree."""
        tree = Tree()
        indi_counter = 0
        fam_counter = 0

        for gedcom_str in gedcom_strings:
            file = io.StringIO(gedcom_str)
            ged = Gedcom(file, tree)

            # Replicate merge logic from mergemyancestors.py
            for _, indi in ged.indi.items():
                fid = indi.fid
                if fid not in tree.indi:
                    indi_counter += 1
                    tree.indi[fid] = Indi(indi.fid, tree, num=indi_counter)
                tree.indi[fid].fams_fid |= indi.fams_fid
                tree.indi[fid].famc_fid |= indi.famc_fid
                tree.indi[fid].name = indi.name
                tree.indi[fid].birthnames |= indi.birthnames
                tree.indi[fid].nicknames |= indi.nicknames
                tree.indi[fid].aka |= indi.aka
                tree.indi[fid].married |= indi.married
                tree.indi[fid].gender = indi.gender
                tree.indi[fid].facts |= indi.facts
                # Manually merge notes to avoid duplication by text content
                for n in indi.notes:
                    if not any(x.text == n.text for x in tree.indi[fid].notes):
                        tree.indi[fid].notes.add(n)
                tree.indi[fid].sources |= indi.sources
                tree.indi[fid].memories |= indi.memories
                tree.indi[fid].baptism = indi.baptism
                tree.indi[fid].confirmation = indi.confirmation
                tree.indi[fid].initiatory = indi.initiatory
                tree.indi[fid].endowment = indi.endowment
                sc = tree.indi[fid].sealing_child
                if not (sc and sc.famc):
                    tree.indi[fid].sealing_child = indi.sealing_child

            for _, fam in ged.fam.items():
                husb, wife = (fam.husb_fid, fam.wife_fid)
                # Use standard ID generation to satisfy Dict[str, Fam] type
                fam_key = Fam.gen_id(tree.indi.get(husb), tree.indi.get(wife))

                if fam_key not in tree.fam:
                    fam_counter += 1
                    tree.fam[fam_key] = Fam(
                        tree.indi.get(husb), tree.indi.get(wife), tree, fam_counter
                    )
                    tree.fam[fam_key].tree = tree
                tree.fam[fam_key].chil_fid |= fam.chil_fid
                if fam.fid:
                    tree.fam[fam_key].fid = fam.fid
                tree.fam[fam_key].facts |= fam.facts
                # Manually merge notes
                for n in fam.notes:
                    if not any(x.text == n.text for x in tree.fam[fam_key].notes):
                        tree.fam[fam_key].notes.add(n)
                tree.fam[fam_key].sources |= fam.sources
                tree.fam[fam_key].sealing_spouse = fam.sealing_spouse

        # Merge notes by text
        tree.notes = sorted(tree.notes, key=lambda x: x.text)  # type: ignore
        for i, n in enumerate(tree.notes):
            if i == 0:
                n.num = 1
                continue
            if n.text == tree.notes[i - 1].text:  # type: ignore
                n.num = tree.notes[i - 1].num  # type: ignore
            else:
                n.num = tree.notes[i - 1].num + 1  # type: ignore

        tree.reset_num()
        return tree

    def _tree_to_gedcom_string(self, tree: Tree) -> str:
        """Convert tree back to GEDCOM string."""
        output = io.StringIO()
        tree.print(output)
        return output.getvalue()

    def test_merge_is_idempotent(self):
        """
        Test that merging A+B then re-merging with A produces no duplicates.

        If merge is idempotent:
            lines(A+B) == lines((A+B)+A)
        """
        # First merge: A + B
        merged_tree = self._merge_gedcoms(self.gedcom_a, self.gedcom_b)
        merged_lines = self._count_data_lines(merged_tree)

        # Get merged output as string
        merged_gedcom = self._tree_to_gedcom_string(merged_tree)

        # Second merge: (A+B) + A again
        remerged_tree = self._merge_gedcoms(merged_gedcom, self.gedcom_a)
        remerged_lines = self._count_data_lines(remerged_tree)

        # They should be equal if merge is idempotent
        self.assertEqual(
            merged_lines,
            remerged_lines,
            f"Merge is not idempotent: original={merged_lines} lines, "
            f"after re-merge with A={remerged_lines} lines (diff={remerged_lines - merged_lines})",
        )

    def test_merge_preserves_individuals(self):
        """Test that merging preserves all individuals without duplication."""
        # Merge A + B
        merged_tree = self._merge_gedcoms(self.gedcom_a, self.gedcom_b)

        # Should have exactly 2 individuals
        self.assertEqual(len(merged_tree.indi), 2, "Expected 2 individuals after merge")

        # Re-merge with A
        merged_gedcom = self._tree_to_gedcom_string(merged_tree)
        remerged_tree = self._merge_gedcoms(merged_gedcom, self.gedcom_a)

        # Should still have exactly 2 individuals
        self.assertEqual(
            len(remerged_tree.indi),
            2,
            f"Expected 2 individuals after re-merge, got {len(remerged_tree.indi)}",
        )

        # Should have exactly 2 families
        self.assertEqual(
            len(merged_tree.fam), 2, "Expected 2 families after merging A+B"
        )

    def test_merge_with_overlap_is_idempotent(self):
        """
        Test merging A+B, then re-merging (A+B) with A again.

        The second merge should not change counts since A already exists.
        This models the stress test scenario.
        """
        # First merge: A + B
        tree1 = self._merge_files(self.file_a, self.file_b)
        indi_count1 = len(tree1.indi)
        fam_count1 = len(tree1.fam)

        # Save merged output
        merged_file = os.path.join(self.temp_dir, "merged.ged")
        self._save_tree(tree1, merged_file)

        # Second merge: (A+B) + A using fresh parse
        tree2 = self._merge_files(merged_file, self.file_a)
        indi_count2 = len(tree2.indi)
        fam_count2 = len(tree2.fam)

        # Individual and family counts should be unchanged
        self.assertEqual(
            indi_count1,
            indi_count2,
            f"Individual count changed: {indi_count1} -> {indi_count2}",
        )
        self.assertEqual(
            fam_count1,
            fam_count2,
            f"Family count changed: {fam_count1} -> {fam_count2}",
        )

    def test_merge_mutually_exclusive_trees(self):
        """
        Test merging two non-overlapping trees produces expected totals.

        If A has 1 person and B has 1 person, merged should have 2.
        """
        tree = self._merge_files(self.file_a, self.file_b)

        self.assertEqual(len(tree.indi), 2, "Expected 2 individuals")
        self.assertEqual(len(tree.fam), 2, "Expected 2 families")

        # Verify the specific individuals exist
        self.assertIn("AAAA-111", tree.indi, "John Doe should be present")
        self.assertIn("BBBB-222", tree.indi, "Jane Smith should be present")

    def test_notes_preserved_after_remerge(self):
        """
        Test that notes are preserved and not duplicated during re-merge.

        This catches the bug where notes were being added to tree.notes
        during parsing even for existing individuals.
        """
        # GEDCOM with notes
        gedcom_with_notes = """0 HEAD
1 SOUR getmyancestors
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Noted/
1 SEX M
1 _FSFTID NOTE-111
1 NOTE This is John's note
0 @N1@ NOTE This is a standalone note
0 TRLR
"""
        file_notes = os.path.join(self.temp_dir, "notes.ged")
        with open(file_notes, "w", encoding="utf-8") as f:
            f.write(gedcom_with_notes)

        # First merge
        tree1 = self._merge_files(file_notes)
        lines1 = self._count_data_lines(tree1)

        # Save and re-merge
        merged_file = os.path.join(self.temp_dir, "merged_notes.ged")
        self._save_tree(tree1, merged_file)

        tree2 = self._merge_files(merged_file, file_notes)
        lines2 = self._count_data_lines(tree2)

        # Line counts should be stable (or very close due to note deduplication)
        self.assertEqual(
            lines1,
            lines2,
            f"Line count changed after re-merge: {lines1} -> {lines2}",
        )

    def test_line_count_stability_with_notes(self):
        """
        Test that line counts remain stable when re-merging files with notes.

        This is a more realistic test that matches the stress test behavior.
        """
        # Create two GEDCOMs with the SAME note text (to test deduplication)
        gedcom_a = """0 HEAD
1 SOUR getmyancestors
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Person /A/
1 SEX M
1 _FSFTID PERS-AAA
1 NOTE Shared note text
0 @F1@ FAM
1 HUSB @I1@
1 _FSFTID FAM_AAA
0 TRLR
"""
        gedcom_b = """0 HEAD
1 SOUR getmyancestors
1 GEDC
2 VERS 5.5
1 CHAR UTF-8
0 @I2@ INDI
1 NAME Person /B/
1 SEX F
1 _FSFTID PERS-BBB
1 NOTE Shared note text
0 @F2@ FAM
1 WIFE @I2@
1 _FSFTID FAM_BBB
0 TRLR
"""
        file_a = os.path.join(self.temp_dir, "line_a.ged")
        file_b = os.path.join(self.temp_dir, "line_b.ged")
        with open(file_a, "w", encoding="utf-8") as f:
            f.write(gedcom_a)
        with open(file_b, "w", encoding="utf-8") as f:
            f.write(gedcom_b)

        # First merge
        tree1 = self._merge_files(file_a, file_b)
        lines1 = self._count_data_lines(tree1)

        # Save and re-merge with A
        merged_file = os.path.join(self.temp_dir, "merged_line.ged")
        self._save_tree(tree1, merged_file)

        tree2 = self._merge_files(merged_file, file_a)
        lines2 = self._count_data_lines(tree2)

        # Line counts should be stable
        self.assertEqual(
            lines1,
            lines2,
            f"Line count not stable: {lines1} -> {lines2} (diff={lines2 - lines1})",
        )

    def _save_tree(self, tree: Tree, filepath: str):
        """Save tree to file."""
        with open(filepath, "w", encoding="utf-8") as f:
            tree.print(f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
