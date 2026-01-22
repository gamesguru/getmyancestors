"""Record classes: Note, Source, Fact, Memorie"""

import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, Dict, Optional
from urllib.parse import unquote, unquote_plus
from xml.etree.ElementTree import Element

from getmyancestors.classes.constants import FACT_EVEN, FACT_TAGS

from .utils import cont

if TYPE_CHECKING:
    from .core import Tree


class Note:
    """GEDCOM Note class"""

    def __init__(self, text="", tree=None, num=None, num_prefix=None, note_type=None):
        self._handle = None
        self.note_type = note_type or "Source Note"
        self.num_prefix = num_prefix
        self.text = text.strip()

        if num:
            self.num = num
        else:
            # Use hash of text for deterministic ID
            self.num = hashlib.md5(self.text.encode("utf-8")).hexdigest()[:10].upper()

        # Restore debug print if verbose
        if tree and hasattr(tree, "fs") and getattr(tree.fs, "verbose", False):
            print(f"##### Creating Note: {num_prefix}, {self.num}", file=sys.stderr)

        if tree:
            if self in tree.notes:
                if hasattr(tree, "fs") and getattr(tree.fs, "verbose", False):
                    preview = (
                        self.text[:60].replace("\n", " ") if self.text else "<EMPTY>"
                    )
                    print(
                        f"♻️  Deduplicated {self.note_type}: ID={self.id} Text='{preview}...' (Prefix={self.num_prefix})",
                        file=sys.stderr,
                    )
            tree.notes.add(self)

    def __eq__(self, other):
        if not isinstance(other, Note):
            return False
        return self.text == other.text and self.num_prefix == other.num_prefix

    def __hash__(self):
        return hash((self.text, self.num_prefix))

    def __str__(self):
        return f"{self.num}. {self.text}"

    @property
    def id(self):
        return (
            f"{self.num_prefix}_{self.num}"
            if self.num_prefix is not None
            else str(self.num)
        )

    def print(self, file=sys.stdout):

        # NOTE: print is not passed tree, so we can't check verbose easily unless we store it.
        # But Note is simple. Maybe skip this one or check global?
        # The user specifically asked for L34.
        file.write(cont("0 @N%s@ NOTE %s" % (self.id, self.text)))

    def link(self, file=sys.stdout, level=1):

        file.write("%s NOTE @N%s@\n" % (level, self.id))

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()
        return self._handle

    def printxml(self, parent_element: Element) -> None:
        note_element = ET.SubElement(
            parent_element,
            "note",
            handle=self.handle,
            id=self.id,
            type="Source Note",
        )
        ET.SubElement(note_element, "text").text = self.text


class Source:
    """GEDCOM Source class"""

    counter: int = 0

    def __init__(self, data=None, tree=None, num=None):
        if num:
            self.num = num
        else:
            Source.counter += 1
            self.num = Source.counter

        self._handle = None
        self.tree = tree
        self.url = self.citation = self.title = self.fid = None
        self.notes = set()
        if data:
            self.fid = data["id"]
            if "about" in data:
                self.url = data["about"].replace(
                    "familysearch.org/platform/memories/memories",
                    "www.familysearch.org/photos/artifacts",
                )
            if "citations" in data:
                self.citation = data["citations"][0]["value"]
            if "titles" in data:
                self.title = data["titles"][0]["value"]
            if "notes" in data:
                notes = [n["text"] for n in data["notes"] if n["text"]]
                for _idx, n in enumerate(notes):
                    self.notes.add(
                        Note(
                            n,
                            self.tree,
                            num=None,
                            note_type="Source Note",
                        )
                    )
            self.modified = data["attribution"]["modified"]

    def __str__(self):
        return f"{self.num}. {self.title}"

    @property
    def id(self):
        return "S" + str(self.fid or self.num)

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()
        return self._handle

    def print(self, file=sys.stdout):
        file.write("0 @S%s@ SOUR \n" % self.id)
        if self.title:
            file.write(cont("1 TITL " + self.title))
        if self.citation:
            file.write(cont("1 AUTH " + self.citation))
        if self.url:
            file.write(cont("1 PUBL " + self.url))
        for n in sorted(self.notes, key=lambda x: x.id or ""):
            n.link(file, 1)
        file.write("1 REFN %s\n" % self.fid)

    def link(self, file=sys.stdout, level=1):
        file.write("%s SOUR @S%s@\n" % (level, self.id))

    def printxml(self, parent_element: Element) -> None:
        source_element = ET.SubElement(
            parent_element,
            "source",
            handle=self.handle,
            change=str(int(self.modified / 1000)),
            id=self.id,
        )
        if self.title:
            ET.SubElement(source_element, "stitle").text = self.title
        if self.citation:
            ET.SubElement(source_element, "sauthor").text = self.citation
        if self.url:
            ET.SubElement(source_element, "spubinfo").text = self.url
        if self.fid:
            ET.SubElement(source_element, "srcattribute", type="REFN", value=self.fid)


class Fact:
    """GEDCOM Fact class"""

    counter: Dict[str, int] = {}

    def __init__(self, data=None, tree: Optional["Tree"] = None, num_prefix=None):
        self.value: Optional[str] = None
        self.type: Optional[str] = None
        self.date: Optional[str] = None
        self.date_type: Optional[str] = None
        self.place = None
        self.note = None
        self.map = None
        self._handle = None
        if data:
            if "value" in data:
                self.value = data["value"]
            if "type" in data:
                self.type = data["type"]
                self.fs_type = self.type
                if self.type in FACT_EVEN and tree and tree.fs:
                    # Cast or ignore, FS session dynamic attr _
                    self.type = tree.fs._(FACT_EVEN[self.type])
                elif self.type[:6] == "data:,":
                    self.type = unquote(self.type[6:])
                elif self.type not in FACT_TAGS:
                    self.type = None

        self.num_prefix = (
            f"{num_prefix}_{FACT_TAGS[self.type]}"
            if num_prefix and self.type in FACT_TAGS
            else num_prefix
        )
        Fact.counter[self.num_prefix or "None"] = (
            Fact.counter.get(self.num_prefix or "None", 0) + 1
        )
        self.num = Fact.counter[self.num_prefix or "None"]
        if data:
            if "date" in data:
                if "formal" in data["date"]:
                    self.date = data["date"]["formal"].split("+")[-1].split("/")[0]
                    if data["date"]["formal"].startswith("A+"):
                        self.date_type = "about"
                    elif data["date"]["formal"].startswith("/+"):
                        self.date_type = "before"
                    elif data["date"]["formal"].endswith("/"):
                        self.date_type = "after"
                else:
                    self.date = data["date"]["original"]
            if "place" in data:
                place = data["place"]
                place_name = place["original"]
                place_id = (
                    place["description"][1:]
                    if "description" in place
                    and tree
                    and place["description"][1:] in (tree.places or [])
                    else None
                )
                # Import Place locally to avoid circular import

                if tree:
                    self.place = tree.ensure_place(place_name, place_id)
                if "changeMessage" in data["attribution"]:
                    self.note = Note(
                        data["attribution"]["changeMessage"],
                        tree,
                        num_prefix="E" + self.num_prefix if self.num_prefix else None,
                        note_type="Event Note",
                    )
            if self.type == "http://gedcomx.org/Death" and not (
                self.date or self.place
            ):
                self.value = "Y"

        if tree:
            tree.facts.add(self)

    @property
    def id(self):
        return (
            f"{self.num_prefix}_{self.num}"
            if self.num_prefix is not None
            else str(self.num)
        )

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()
        return self._handle

    def __eq__(self, other):
        """Facts are equal if type, date, date_type, place, and value match."""
        if not isinstance(other, Fact):
            return False
        # Compare by semantic content, not object identity
        place_name = self.place.name if self.place else None
        other_place_name = other.place.name if other.place else None
        return (
            self.type == other.type
            and self.date == other.date
            and self.date_type == other.date_type
            and place_name == other_place_name
            and self.value == other.value
            and (self.note.text if self.note else None)
            == (other.note.text if other.note else None)
        )

    def __hash__(self):
        """Hash based on semantic content for set deduplication."""
        place_name = self.place.name if self.place else None
        return hash(
            (
                self.type,
                self.date,
                self.date_type,
                place_name,
                self.value,
                self.note.text if self.note else None,
            )
        )

    def printxml(self, parent_element):
        event_element = ET.SubElement(
            parent_element,
            "event",
            handle=self.handle,
            id=self.id,
        )
        ET.SubElement(event_element, "type").text = (
            unquote_plus(self.type[len("http://gedcomx.org/") :])
            if self.type and self.type.startswith("http://gedcomx.org/")
            else self.type
        )
        if self.date:
            params: Dict[str, Any] = {"val": self.date}
            if self.date_type is not None:
                params["type"] = self.date_type
            ET.SubElement(event_element, "datestr", **params)
        if self.place:
            ET.SubElement(event_element, "place", hlink=self.place.handle)
        if self.note:
            ET.SubElement(event_element, "noteref", hlink=self.note.handle)

    def print(self, file):
        if self.type in FACT_TAGS:
            tmp = "1 " + FACT_TAGS[self.type]
            if self.value:
                tmp += " " + self.value
            file.write(cont(tmp))
        elif self.type:
            file.write("1 EVEN\n2 TYPE %s\n" % self.type)
            if self.value:
                file.write(cont("2 NOTE Description: " + self.value))
        else:
            return
        if self.date:
            file.write(cont("2 DATE " + self.date))
        if self.place:
            self.place.print(file, 2)
        if self.map:
            latitude, longitude = self.map
            file.write("3 MAP\n4 LATI %s\n4 LONG %s\n" % (latitude, longitude))
        if self.note:
            self.note.link(file, 2)


class Memorie:
    """GEDCOM Memorie class"""

    def __init__(self, data=None):
        self.description = self.url = None
        if data and "links" in data:
            self.url = data["about"]
            if "titles" in data:
                self.description = data["titles"][0]["value"]
            if "descriptions" in data:
                self.description = (
                    "" if not self.description else self.description + "\n"
                ) + data["descriptions"][0]["value"]

    def print(self, file):
        file.write("1 OBJE\n2 FORM URL\n")
        if self.description:
            file.write(cont("2 TITL " + self.description))
        if self.url:
            file.write(cont("2 FILE " + self.url))
