#!/usr/bin/env python3
# coding: utf-8
import os
import sys
from datetime import datetime
from typing import Any, List, Optional

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

import typer

from getmyancestors.classes.gedcom import Gedcom
from getmyancestors.classes.tree import Fam, Indi, Tree

# Hack to play nice in script mode
sys.path.append(os.path.dirname(sys.argv[0]))

app = typer.Typer(
    help="Merge GEDCOM data from FamilySearch Tree (4 Jul 2016)",
    add_completion=True,
    no_args_is_help=False,  # script might be piped stdin
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _warn(msg: str):
    """Write a warning message to stderr with optional color (if TTY)."""
    use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
    if use_color:
        sys.stderr.write(f"\033[33m{msg}\033[0m\n")
    else:
        sys.stderr.write(f"{msg}\n")


@app.command()
def main(
    files: Annotated[
        Optional[List[str]],
        typer.Option("-i", metavar="<FILE>", help="input GEDCOM files [stdin]"),
    ] = None,
    outfile: Annotated[
        Optional[str],
        typer.Option("-o", metavar="<FILE>", help="output GEDCOM files [stdout]"),
    ] = None,
    creation_date: Annotated[
        Optional[str],
        typer.Option(
            "--creation-date",
            metavar="<ISO8601>",
            help="Override creation date in GEDCOM header (YYYY-MM-DDTHH:MM:SS)",
        ),
    ] = None,
    extra_files: List[str] = typer.Argument(None, hidden=True),
):
    """
    Merge GEDCOM data from FamilySearch Tree
    """
    if extra_files:
        if files is None:
            files = []
        files.extend(extra_files)

    # Force generic usage usage help logic if needed, but Typer handles it.

    creation_dt = None
    if creation_date:
        try:
            creation_dt = datetime.fromisoformat(creation_date)
        except ValueError:
            print(
                f"Invalid creation date format: {creation_date}. Expected ISO 8601 (YYYY-MM-DDTHH:MM:SS)",
                file=sys.stderr,
            )
            raise typer.Exit(code=1) from None

    tree = Tree(creation_date=creation_dt)

    # Track used IDs to prevent collisions when merging multiple files
    used_indi_nums = set()
    used_fam_nums = set()

    # Determine input sources
    input_handles: List[Any] = []
    if files:
        for fpath in files:
            try:
                # Open in read mode with utf-8 encoding
                # pylint: disable=consider-using-with
                f = open(fpath, "r", encoding="UTF-8")
                input_handles.append(f)
            except OSError as e:
                print(f"Error opening file {fpath}: {e}", file=sys.stderr)
                raise typer.Exit(code=2) from None
    else:
        # Default to stdin
        input_handles.append(sys.stdin)

    try:
        # read the GEDCOM data
        for file in input_handles:
            # Determine filename for logging
            filename = getattr(file, "name", "stdin")
            # If it's a relative path, might want basename to keep it short
            if filename != "stdin":
                filename = os.path.basename(filename)

            ged = Gedcom(file, tree)

            # Deduplicate names by string representation
            def merge_names(target_set, source_set):
                target_set.update(source_set)

            # Helper for whitespace normalization in quotes
            def norm_space(s):
                return " ".join(s.split()) if s else ""

            # add information about individuals
            new_indi = 0
            merged_indi = 0
            for fid, indi in sorted(ged.indi.items()):
                if fid not in tree.indi:
                    new_indi += 1

                    # Try to reuse the original GEDCOM ID (indi.num)
                    # If it collides with an existing ID in the merged tree, generate a new one
                    candidate_num = indi.num
                    original_candidate = candidate_num
                    suffix_counter = 1
                    while candidate_num in used_indi_nums:
                        # Collision detected! Append suffix
                        candidate_num = f"{original_candidate}_{suffix_counter}"
                        suffix_counter += 1

                    used_indi_nums.add(candidate_num)
                    tree.indi[fid] = Indi(indi.fid, tree, num=candidate_num)

                    # Track origin file
                    tree.indi[fid].origin_file = filename
                else:
                    merged_indi += 1

                # UNION data from both sources (superset)
                tree.indi[fid].fams_fid |= indi.fams_fid
                tree.indi[fid].famc_fid |= indi.famc_fid

                merge_names(tree.indi[fid].birthnames, indi.birthnames)
                merge_names(tree.indi[fid].nicknames, indi.nicknames)
                merge_names(tree.indi[fid].aka, indi.aka)
                merge_names(tree.indi[fid].married, indi.married)

                # Deduplicate facts by type/date/value/place
                existing_facts = {
                    (f.type, f.date, f.value, f.place.name if f.place else None)
                    for f in tree.indi[fid].facts
                }
                # Sort facts to ensure deterministic winner on collision
                for f in sorted(
                    indi.facts,
                    key=lambda fa: (
                        fa.type or "",
                        fa.date or "",
                        fa.value or "",
                        fa.place.name if fa.place else "",
                        fa.note.text if fa.note else "",
                    ),
                ):
                    fact_key = (
                        f.type,
                        f.date,
                        f.value,
                        f.place.name if f.place else None,
                    )
                    if fact_key not in existing_facts:
                        tree.indi[fid].facts.add(f)
                        existing_facts.add(fact_key)

                # Manually merge notes to avoid duplication by text content
                # Sort notes for consistent order (though order in SET doesn't matter, processing order might)
                for n in sorted(indi.notes, key=lambda note: note.text or ""):
                    is_dup = any(x.text == n.text for x in tree.indi[fid].notes)
                    if not is_dup:
                        tree.indi[fid].notes.add(n)

                # Deduplicate sources by (source.fid, normalized_quote)
                existing_sources = {
                    (s.fid, norm_space(q)) for s, q in tree.indi[fid].sources
                }
                # Sort sources
                for s, q in sorted(
                    indi.sources,
                    key=lambda src: (
                        src[0].title or "",
                        src[0].fid or "",
                        src[1] or "",
                    ),
                ):
                    source_key = (s.fid, norm_space(q))
                    if source_key not in existing_sources:
                        tree.indi[fid].sources.add((s, q))
                        existing_sources.add(source_key)

                # Deduplicate memories by URL (primary) or Description (fallback)
                def get_mem_key(mem):
                    return mem.url if mem.url else (None, mem.description)

                existing_memories = {get_mem_key(m) for m in tree.indi[fid].memories}
                # Sort memories
                for m in sorted(
                    indi.memories,
                    key=lambda mem: (mem.url or "", mem.description or ""),
                ):
                    key = get_mem_key(m)
                    if key not in existing_memories:
                        tree.indi[fid].memories.add(m)
                        existing_memories.add(key)

                # Update ordinance fields if they are missing in the target
                if not tree.indi[fid].baptism:
                    tree.indi[fid].baptism = indi.baptism
                if not tree.indi[fid].confirmation:
                    tree.indi[fid].confirmation = indi.confirmation
                if not tree.indi[fid].initiatory:
                    tree.indi[fid].initiatory = indi.initiatory
                if not tree.indi[fid].endowment:
                    tree.indi[fid].endowment = indi.endowment
                if not tree.indi[fid].sealing_child:
                    tree.indi[fid].sealing_child = indi.sealing_child

                # Only update simple fields if they are missing (first file wins for stability)
                if not tree.indi[fid].name:
                    tree.indi[fid].name = indi.name
                if not tree.indi[fid].gender:
                    tree.indi[fid].gender = indi.gender

            # add information about families
            # Key by fam.fid to preserve unique family records
            # (keying by (husb, wife) incorrectly merges different families with same parents)
            new_fam = 0
            merged_fam = 0
            for fid, fam in sorted(ged.fam.items()):
                if fid not in tree.fam:
                    new_fam += 1

                    # Try to reuse the original GEDCOM ID (fam.num)
                    candidate_num = fam.num
                    original_candidate = candidate_num
                    suffix_counter = 1
                    while candidate_num in used_fam_nums:
                        candidate_num = f"{original_candidate}_{suffix_counter}"
                        suffix_counter += 1

                    used_fam_nums.add(candidate_num)

                    tree.fam[fid] = Fam(
                        tree.indi.get(fam.husb_fid),
                        tree.indi.get(fam.wife_fid),
                        tree,
                        candidate_num,
                    )
                    tree.fam[fid].tree = tree
                    # Track origin file
                    tree.fam[fid].origin_file = filename

                    # Copy husb_fid/wife_fid for proper linking later
                    tree.fam[fid].husb_fid = fam.husb_fid
                    tree.fam[fid].wife_fid = fam.wife_fid
                else:
                    merged_fam += 1

                # UNION data
                # Deduplicate facts
                existing_facts = {
                    (f.type, f.date, f.value, f.place.name if f.place else None)
                    for f in tree.fam[fid].facts
                }
                for f in sorted(
                    fam.facts,
                    key=lambda fa: (
                        fa.type or "",
                        fa.date or "",
                        fa.value or "",
                        fa.place.name if fa.place else "",
                        fa.note.text if fa.note else "",
                    ),
                ):
                    fact_key = (
                        f.type,
                        f.date,
                        f.value,
                        f.place.name if f.place else None,
                    )
                    if fact_key not in existing_facts:
                        tree.fam[fid].facts.add(f)
                        existing_facts.add(fact_key)

                # Manually merge notes
                for n in sorted(fam.notes, key=lambda note: note.text or ""):
                    if not any(x.text == n.text for x in tree.fam[fid].notes):
                        tree.fam[fid].notes.add(n)

                # Deduplicate sources

                existing_sources = {
                    (s.fid, norm_space(q)) for s, q in tree.fam[fid].sources
                }
                for s, q in sorted(
                    fam.sources,
                    key=lambda src: (
                        src[0].title or "",
                        src[0].fid or "",
                        src[1] or "",
                    ),
                ):
                    source_key = (s.fid, norm_space(q))
                    if source_key not in existing_sources:
                        tree.fam[fid].sources.add((s, q))
                        existing_sources.add(source_key)

                if not tree.fam[fid].sealing_spouse:
                    tree.fam[fid].sealing_spouse = fam.sealing_spouse

                if not tree.fam[fid].fid:
                    tree.fam[fid].fid = fam.fid

                # Always merge children - set union prevents duplicates
                tree.fam[fid].chil_fid |= fam.chil_fid

        # Notes already have stable IDs from content hashing in classes/tree/records.py
        # No renumbering needed.

        # Link families to individuals and vice versa
        # This creates the actual object references needed for GEDCOM output
        for _fam_fid, fam in tree.fam.items():
            # Link husband to this family
            if fam.husb_fid and fam.husb_fid in tree.indi:
                fam.husband = tree.indi[fam.husb_fid]
                tree.indi[fam.husb_fid].fams.add(fam)
            # Link wife to this family
            if fam.wife_fid and fam.wife_fid in tree.indi:
                fam.wife = tree.indi[fam.wife_fid]
                tree.indi[fam.wife_fid].fams.add(fam)
            # Link children to this family
            for chil_fid in fam.chil_fid:
                if chil_fid in tree.indi:
                    fam.children.add(tree.indi[chil_fid])
                    tree.indi[chil_fid].famc.add(fam)

        # compute number for family relationships and print GEDCOM file
        tree.reset_num()

        if outfile:
            try:
                with open(outfile, "w", encoding="UTF-8") as out:
                    tree.print(out)
            except OSError as e:
                print(f"Error opening output file {outfile}: {e}", file=sys.stderr)
                raise typer.Exit(code=2) from None
        else:
            tree.print(sys.stdout)

    finally:
        # Close handles that are not stdin
        for f in input_handles:
            if f is not sys.stdin:
                f.close()


if __name__ == "__main__":
    app()
