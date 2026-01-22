"""Element classes: Name, Place, Ordinance, Citation"""

import os
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional
from xml.etree.ElementTree import Element

from getmyancestors.classes.constants import ORDINANCES_STATUS

from .records import Note
from .utils import NAME_MAP, cont


class Name:
    """GEDCOM Name class"""

    def __init__(
        self, data=None, tree=None, owner_fis=None, kind=None, alternative: bool = False
    ):
        self.given = ""
        self.surname = ""
        self.prefix = None
        self.suffix = None
        self.note = None
        self.alternative = alternative
        self.owner_fis = owner_fis
        self.kind = kind
        if data:
            if "parts" in data["nameForms"][0]:
                for z in data["nameForms"][0]["parts"]:
                    if z["type"] == "http://gedcomx.org/Given":
                        self.given = z["value"]
                    if z["type"] == "http://gedcomx.org/Surname":
                        self.surname = z["value"]
                    if z["type"] == "http://gedcomx.org/Prefix":
                        self.prefix = z["value"]
                    if z["type"] == "http://gedcomx.org/Suffix":
                        self.suffix = z["value"]
            if "changeMessage" in data.get("attribution", {}):
                self.note = Note(
                    data["attribution"]["changeMessage"],
                    tree,
                    note_type="Name Note",
                )

    def __str__(self):
        return f"{self.given} {self.surname}"

    def __eq__(self, other):
        if not isinstance(other, Name):
            return NotImplemented
        return (
            self.given == other.given
            and self.surname == other.surname
            and self.prefix == other.prefix
            and self.suffix == other.suffix
            and self.kind == other.kind
            and self.alternative == other.alternative
            and (self.note.text if self.note else None)
            == (other.note.text if other.note else None)
        )

    def __hash__(self):
        return hash(
            (
                self.given,
                self.surname,
                self.prefix,
                self.suffix,
                self.kind,
                self.alternative,
                self.note.text if self.note else None,
            )
        )

    def printxml(self, parent_element):
        params = {}
        if self.kind is not None:
            params["type"] = NAME_MAP.get(self.kind, self.kind)
        if self.alternative:
            params["alt"] = "1"
        person_name = ET.SubElement(parent_element, "name", **params)
        ET.SubElement(person_name, "first").text = self.given
        ET.SubElement(person_name, "surname").text = self.surname
        # TODO prefix / suffix

    def print(self, file=sys.stdout, typ=None):
        tmp = "1 NAME %s /%s/" % (self.given, self.surname)
        if self.suffix:
            tmp += " " + self.suffix
        file.write(cont(tmp))
        if typ:
            file.write("2 TYPE %s\n" % typ)
        if self.prefix:
            file.write("2 NPFX %s\n" % self.prefix)
        if self.note:
            self.note.link(file, 2)


class Place:
    """GEDCOM Place class"""

    counter = 0

    def __init__(
        self,
        place_id: str,
        name: str,
        place_type: Optional[str] = None,
        parent: Optional["Place"] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ):
        self._handle: Optional[str] = None
        self.name = name
        self.type = place_type
        self.id = place_id
        self.parent = parent
        self.latitude = latitude
        self.longitude = longitude

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()
        return self._handle

    def print(self, file, indentation=0):
        file.write("%d @P%s@ PLAC %s\n" % (indentation, self.id, self.name))

    def __eq__(self, other):
        if not isinstance(other, Place):
            return NotImplemented
        return self.name == other.name and self.id == other.id

    def __hash__(self):
        return hash((self.name, self.id))

    def printxml(self, parent_element):
        place_element = ET.SubElement(
            parent_element,
            "placeobj",
            handle=self.handle,
            id=self.id,
            type=self.type or "Unknown",
        )
        ET.SubElement(place_element, "pname", value=self.name)
        if self.parent:
            ET.SubElement(place_element, "placeref", hlink=self.parent.handle)
        if self.latitude is not None and self.longitude is not None:
            ET.SubElement(
                place_element, "coord", long=str(self.longitude), lat=str(self.latitude)
            )


class Ordinance:
    """GEDCOM Ordinance class"""

    def __init__(self, data=None):
        self.date = self.temple_code = self.status = self.famc = None
        if data:
            if "completedDate" in data:
                self.date = data["completedDate"]
            if "completedTemple" in data:
                self.temple_code = data["completedTemple"]["code"]
            self.status = data.get("status")

    def print(self, file):
        if self.date:
            file.write(cont("2 DATE " + self.date))
        if self.temple_code:
            file.write("2 TEMP %s\n" % self.temple_code)
        if self.status in ORDINANCES_STATUS:
            file.write("2 STAT %s\n" % ORDINANCES_STATUS[self.status])
        if self.famc:
            file.write("2 FAMC @F%s@\n" % self.famc.num)


class Citation:
    """Citation class"""

    def __init__(self, data: Dict[str, Any], source):
        self._handle: Optional[str] = None
        self.id = data["id"]
        self.source = source
        attr = data.get("attribution", {})
        self.message = attr.get("changeMessage")
        self.modified = attr.get("modified")

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()
        return self._handle

    def printxml(self, parent_element: Element):
        citation_element = ET.SubElement(
            parent_element,
            "citation",
            handle=self.handle,
            change=str(int(self.modified / 1000)),
            id="C" + str(self.id),
        )
        ET.SubElement(citation_element, "confidence").text = "2"
        ET.SubElement(citation_element, "sourceref", hlink=self.source.handle)
