"""Core classes: Indi, Fam, Tree"""

import asyncio
import hashlib
import os
import sys
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from enum import Enum
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Set, Tuple, Union

# global imports
import babelfish
import geocoder
from requests_cache import CachedSession

# local imports
from getmyancestors import __version__
from getmyancestors.classes.constants import MAX_PERSONS
from getmyancestors.classes.session import GMASession
from getmyancestors.classes.tree.utils import warn

from .elements import Citation, Name, Ordinance, Place
from .records import Fact, Memorie, Note, Source
from .utils import GEONAME_FEATURE_MAP, cont

# pylint: disable=too-many-lines


class ParentRelType(Enum):
    """Parent-child relationship type for GEDCOM PEDI tag"""

    BIRTH = "birth"
    ADOPTED = "adopted"
    STEP = "step"
    FOSTER = "foster"

    @classmethod
    def from_fs_type(
        cls, facts: Optional[List[Dict[str, Any]]]
    ) -> Optional["ParentRelType"]:
        """Convert FamilySearch relationship facts to ParentRelType"""
        if not facts:
            return None

        mapping = {
            "http://gedcomx.org/BiologicalParent": cls.BIRTH,
            "http://gedcomx.org/AdoptiveParent": cls.ADOPTED,
            "http://gedcomx.org/StepParent": cls.STEP,
            "http://gedcomx.org/FosterParent": cls.FOSTER,
        }

        for fact in facts:
            f_type = fact.get("type")
            if f_type in mapping:
                return mapping[f_type]

        # Failed to find a match, return unknown type
        return None


class Indi:
    """GEDCOM individual class
    :param fid: FamilySearch id
    :param tree: a tree object
    :param num: the GEDCOM identifier
    """

    counter = 0

    def __init__(
        self, fid: Optional[str] = None, tree: Optional["Tree"] = None, num=None
    ):
        self._handle: Optional[str] = None
        if num:
            self.num = num
        else:
            Indi.counter += 1
            self.num = Indi.counter
        self.fid = fid
        self.tree = tree
        self.num_prefix = "I"
        self.origin_file: Optional[str] = None
        self.famc: Set[Tuple["Fam", Optional[ParentRelType]]] = set()
        self.fams: Set["Fam"] = set()
        self.famc_fid: Set[str] = set()
        self.fams_fid: Set[str] = set()
        self.famc_num: Set[int] = set()
        self.fams_num: Set[int] = set()
        self.famc_ids: Set[str] = set()
        self.fams_ids: Set[str] = set()
        self.name: Optional[Name] = None
        self.gender: Optional[str] = None
        self.living: Optional[bool] = None
        # (father_id, mother_id, father_rel_type, mother_rel_type)
        self.parents: Set[
            Tuple[
                Optional[str],
                Optional[str],
                Optional[ParentRelType],
                Optional[ParentRelType],
            ]
        ] = set()
        self.spouses: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = (
            set()
        )  # (person1, person2, relfid)
        self.children: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = (
            set()
        )  # (father_id, mother_id, child_id)
        self.baptism: Optional[Ordinance] = None
        self.confirmation: Optional[Ordinance] = None
        self.initiatory: Optional[Ordinance] = None
        self.endowment: Optional[Ordinance] = None
        self.sealing_child: Optional[Ordinance] = None
        self.nicknames: Set[Name] = set()
        self.birthnames: Set[Name] = set()
        self.married: Set[Name] = set()
        self.aka: Set[Name] = set()
        self.facts: Set[Fact] = set()
        self.notes: Set[Note] = set()
        self.sources: Set[Tuple[Source, Optional[str]]] = set()
        self.citations: Set[Citation] = set()
        self.memories: Set[Memorie] = set()

    def __str__(self):
        """Return readable string for debugging/reference purposes."""
        return f"{self.num}. {self.name}, fam: {self.fid}"

    def add_data(self, data):
        """add FS individual data"""
        if data:
            self.living = data["living"]
            for x in data["names"]:
                alt = not x.get("preferred", False)
                if x["type"] == "http://gedcomx.org/Nickname":
                    self.nicknames.add(Name(x, self.tree, self.fid, "nickname", alt))
                elif x["type"] == "http://gedcomx.org/BirthName":
                    self.birthnames.add(Name(x, self.tree, self.fid, "birthname", alt))
                elif x["type"] == "http://gedcomx.org/AlsoKnownAs":
                    self.aka.add(Name(x, self.tree, self.fid, "aka", alt))
                elif x["type"] == "http://gedcomx.org/MarriedName":
                    self.married.add(Name(x, self.tree, self.fid, "married", alt))
                else:
                    print("Unknown name type: " + x.get("type"), file=sys.stderr)
                    raise ValueError("Unknown name type")
            if "gender" in data:
                if data["gender"]["type"] == "http://gedcomx.org/Male":
                    self.gender = "M"
                elif data["gender"]["type"] == "http://gedcomx.org/Female":
                    self.gender = "F"
                elif data["gender"]["type"] == "http://gedcomx.org/Unknown":
                    self.gender = "U"
            if "facts" in data:
                for x in data["facts"]:
                    if x["type"] == "http://familysearch.org/v1/LifeSketch":
                        self.notes.add(
                            Note(
                                "=== %s ===\n%s"
                                % (
                                    (
                                        self.tree.fs._("Life Sketch")
                                        if self.tree and self.tree.fs
                                        else "Life Sketch"
                                    ),
                                    x.get("value", ""),
                                ),
                                self.tree,
                                num_prefix=f"INDI_{self.fid}",
                                note_type="Person Note",
                            )
                        )
                    else:
                        self.facts.add(
                            Fact(x, self.tree, num_prefix=f"INDI_{self.fid}")
                        )
        if "sources" in data and self.tree and self.tree.fs:
            sources = self.tree.fs.get_url(
                "/platform/tree/persons/%s/sources" % self.fid
            )
            if sources:
                for quote in sources["persons"][0]["sources"]:
                    source_id = quote["descriptionId"]
                    source_data = next(
                        (
                            s
                            for s in sources["sourceDescriptions"]
                            if s["id"] == source_id
                        ),
                        None,
                    )
                    if self.tree:
                        if source_data:
                            source = self.tree.ensure_source(source_data)
                        else:
                            existing_source = self.tree.sources.get(source_id)
                            if existing_source:
                                source = existing_source
                            else:
                                source = self.tree.ensure_source({"id": source_id})
                    else:
                        source = None
                        if source and self.tree:
                            citation = self.tree.ensure_citation(quote, source)
                            self.citations.add(citation)
                            self.sources.add((source, citation.message))

            for evidence in data.get("evidence", []):
                memory_id, *_ = evidence["id"].partition("-")
                url = "/platform/memories/memories/%s" % memory_id
                memorie = (
                    self.tree.fs.get_url(url) if self.tree and self.tree.fs else None
                )
                if memorie and "sourceDescriptions" in memorie:
                    for x in memorie["sourceDescriptions"]:
                        if x["mediaType"] == "text/plain":
                            text = "\n".join(
                                val.get("value", "")
                                for val in x.get("titles", [])
                                + x.get("descriptions", [])
                            )
                            self.notes.add(
                                Note(
                                    text,
                                    self.tree,
                                    num_prefix=f"INDI_{self.fid}",
                                    note_type="Person Note",
                                )
                            )
                        else:
                            self.memories.add(Memorie(x))

    def add_fams(self, fam: "Fam"):
        """add family fid (for spouse or parent)"""
        self.fams.add(fam)

    def add_famc(self, fam: "Fam", rel_type: Optional[ParentRelType] = None):
        """add family fid (for child) with optional relationship type"""
        self.famc.add((fam, rel_type))

    def get_notes(self):
        """retrieve individual notes"""
        name_str = str(self.name) if self.name else "Unknown"
        print(
            f"Getting Notes for {self.fid} {name_str}",
            file=sys.stderr,
        )
        if not self.tree or not self.tree.fs:
            return
        notes = self.tree.fs.get_url("/platform/tree/persons/%s/notes" % self.fid)
        if notes:
            for n in notes["persons"][0]["notes"]:
                text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                text_note += n["text"] + "\n" if "text" in n else ""
                self.notes.add(
                    Note(
                        text_note,
                        self.tree,
                        num_prefix=f"INDI_{self.fid}",
                        note_type="Person Note",
                    )
                )

    def get_ordinances(self):
        """retrieve LDS ordinances
        need a LDS account
        """
        res: List[Any] = []
        famc: Union[bool, Tuple[str, str]] = False
        if self.living:
            return res, famc
        if not self.tree or not self.tree.fs:
            return res, famc
        url = "/service/tree/tree-data/reservations/person/%s/ordinances" % self.fid
        data = self.tree.fs.get_url(url, {}, no_api=True)
        if data:
            for key, o in data["data"].items():
                if key == "baptism":
                    self.baptism = Ordinance(o)
                elif key == "confirmation":
                    self.confirmation = Ordinance(o)
                elif key == "initiatory":
                    self.initiatory = Ordinance(o)
                elif key == "endowment":
                    self.endowment = Ordinance(o)
                elif key == "sealingsToParents":
                    for subo in o:
                        self.sealing_child = Ordinance(subo)
                        relationships = subo.get("relationships", {})
                        father = relationships.get("parent1Id")
                        mother = relationships.get("parent2Id")
                        if father and mother:
                            famc = father, mother
                elif key == "sealingsToSpouses":
                    res += o
        return res, famc

    @property
    def id(self):
        return self.fid or self.num

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()

        return self._handle

    def printxml(self, parent_element):
        # <person handle="_fa593c2779e5ed1c947416cba9e" change="1720382301" id="IL43B-D2H">
        #     <gender>M</gender>
        #     <name type="Birth Name">
        #         <first>József</first>
        #         <surname>Cser</surname>
        #         <noteref hlink="_fa593c277f7c527e3afe4623b9"/>
        #     </name>
        #     <eventref hlink="_fa593c277a0712aa4241bbf47db" role="Primary"/>
        #     <attribute type="_FSFTID" value="L43B-D2H"/>
        #     <childof hlink="_fa593c277af212e6c1f9f44bc4a"/>
        #     <parentin hlink="_fa593c277af72c83e0e3fbf6ed2"/>
        #     <citationref hlink="_fa593c277b7715371c26d1b0a81"/>
        # </person>
        person = ET.SubElement(
            parent_element,
            "person",
            handle=self.handle,
            # change='1720382301',
            id="I" + str(self.id),
        )
        if self.fid:
            # Add custom attribute for FamilySearch ID
            ET.SubElement(person, "attribute", type="_FSFTID", value=self.fid)

        if self.name:
            self.name.printxml(person)
        for name in self.nicknames | self.birthnames | self.aka | self.married:
            name.printxml(person)

        gender = ET.SubElement(person, "gender")
        gender.text = self.gender

        if self.fams:
            for fam in self.fams:
                ET.SubElement(person, "parentin", hlink=fam.handle)

        if self.famc:
            for fam, _rel_type in self.famc:
                ET.SubElement(person, "childof", hlink=fam.handle)

        for fact in self.facts:
            ET.SubElement(person, "eventref", hlink=fact.handle, role="Primary")

        for citation in self.citations:
            ET.SubElement(person, "citationref", hlink=citation.handle)

        for note in self.notes:
            ET.SubElement(person, "noteref", hlink=note.handle)

    #   <noteref hlink="_fac4a686369713d9cd55159ada9"/>
    #   <citationref hlink="_fac4a72a01b1681293ea1ee8d9"/>

    def get_contributors(self):
        """retrieve contributors"""
        if self.fid and self.tree:
            url = "/platform/tree/persons/%s/changes" % self.fid
            text = self.tree.get_contributors_text(url)
            if text:
                for n in self.tree.notes:
                    if n.text == text:
                        self.notes.add(n)
                        return
                self.notes.add(Note(text, self.tree))

    def print(self, file=sys.stdout):
        """print individual in GEDCOM format"""
        file.write("0 @I%s@ INDI\n" % self.id)
        if self.name:
            self.name.print(file)
        for nick in sorted(
            self.nicknames,
            key=lambda x: (
                x.given or "",
                x.surname or "",
                x.prefix or "",
                x.suffix or "",
                x.kind or "",
                str(x.alternative),
                x.note.text if x.note else "",
            ),
        ):
            file.write(cont("2 NICK %s %s" % (nick.given, nick.surname)))
        for birthname in sorted(
            self.birthnames,
            key=lambda x: (
                x.given or "",
                x.surname or "",
                x.prefix or "",
                x.suffix or "",
                x.kind or "",
                str(x.alternative),
                x.note.text if x.note else "",
            ),
        ):
            birthname.print(file)
        for aka in sorted(
            self.aka,
            key=lambda x: (
                x.given or "",
                x.surname or "",
                x.prefix or "",
                x.suffix or "",
                x.kind or "",
                str(x.alternative),
                x.note.text if x.note else "",
            ),
        ):
            aka.print(file, "aka")
        for married_name in sorted(
            self.married,
            key=lambda x: (
                x.given or "",
                x.surname or "",
                x.prefix or "",
                x.suffix or "",
                x.kind or "",
                str(x.alternative),
                x.note.text if x.note else "",
            ),
        ):
            married_name.print(file, "married")
        if self.gender:
            file.write("1 SEX %s\n" % self.gender)
        for fact in sorted(
            self.facts,
            key=lambda x: (
                x.date or "9999",
                x.type or "",
                x.value or "",
                x.place.id if x.place else "",
                x.note.text if x.note else "",
            ),
        ):
            fact.print(file)
        for memory in sorted(
            self.memories, key=lambda x: (x.url or "", x.description or "")
        ):
            memory.print(file)
        if self.baptism:
            file.write("1 BAPL\n")
            self.baptism.print(file)
        if self.confirmation:
            file.write("1 CONL\n")
            self.confirmation.print(file)
        if self.initiatory:
            file.write("1 WAC\n")
            self.initiatory.print(file)
        if self.endowment:
            file.write("1 ENDL\n")
            self.endowment.print(file)
        if self.sealing_child:
            file.write("1 SLGC\n")
            self.sealing_child.print(file)
        for fam in sorted(self.fams, key=lambda x: x.id or ""):
            file.write("1 FAMS @F%s@\n" % fam.id)
        for fam, rel_type in sorted(self.famc, key=lambda x: x[0].id or ""):
            file.write("1 FAMC @F%s@\n" % fam.id)
            # Output PEDI tag for explicit relationship type
            if rel_type:
                file.write("2 PEDI %s\n" % rel_type.value)
            else:
                warn(f"Missing PEDI type for {self.fid} in family {fam.id}")
        # print(f'Fams Ids: {self.fams_ids}, {self.fams_fid}, {self.fams_num}', file=sys.stderr)
        # for num in self.fams_ids:
        # print(f'Famc Ids: {self.famc_ids}', file=sys.stderr)
        # for num in self.famc_ids:
        # file.write("1 FAMC @F%s@\n" % num)
        file.write("1 _FSFTID %s\n" % self.fid)
        for note in sorted(self.notes, key=lambda x: x.id or ""):
            note.link(file)
        for source, quote in sorted(
            self.sources, key=lambda x: (x[0].id or "", x[1] or "")
        ):
            source.link(file, 1)
            if quote:
                file.write(cont("2 PAGE " + quote))


class Fam:
    """GEDCOM family class
    :param husb: husbant fid
    :param wife: wife fid
    :param tree: a Tree object
    :param num: a GEDCOM identifier
    """

    counter = 0

    def __init__(
        self,
        husband: Optional[Indi] = None,
        wife: Optional[Indi] = None,
        tree: Optional["Tree"] = None,
        num=None,
    ):
        self._handle: Optional[str] = None
        self.num = num if num else Fam.gen_id(husband, wife)
        self.fid: Optional[str] = None
        self._husband = husband
        self._wife = wife
        self.tree = tree
        self.num_prefix = "F"
        self.origin_file: Optional[str] = None
        self.children: Set[Indi] = set()
        self.facts: Set[Fact] = set()
        self.sealing_spouse: Optional[Ordinance] = None
        self.husb_num: Optional[str] = None
        self.wife_num: Optional[str] = None
        self.chil_num: Set[str] = set()
        self.husb_fid: Optional[str] = None
        self.wife_fid: Optional[str] = None
        self.chil_fid: Set[str] = set()
        self.notes: Set[Note] = set()
        self.sources: Set[Tuple[Source, Optional[str]]] = set()

    @property
    def husband(self):
        """get husband"""
        if self._husband:
            return self._husband
        if self.husb_num and self.tree and self.husb_num in self.tree.indi:
            return self.tree.indi.get(self.husb_num)
        return None

    @husband.setter
    def husband(self, value):
        """set husband"""
        self._husband = value

    @property
    def wife(self):
        """get wife"""
        if self._wife:
            return self._wife
        if self.wife_num and self.tree and self.wife_num in self.tree.indi:
            return self.tree.indi.get(self.wife_num)
        return None

    @wife.setter
    def wife(self, value):
        """set wife"""
        self._wife = value

    @property
    def handle(self):
        if not self._handle:
            self._handle = "_" + os.urandom(10).hex()

        return self._handle

    @staticmethod
    def gen_id(husband: Indi | None, wife: Indi | None) -> str:
        if husband and wife:
            return f"FAM_{husband.id}-{wife.id}"
        if husband:
            return f"FAM_{husband.id}-UNK"
        if wife:
            return f"FAM_UNK-{wife.id}"

        Fam.counter += 1
        return f"FAM_UNK-UNK-{Fam.counter}"

    def add_child(self, child: Indi | None):
        """add a child fid to the family"""
        if child is not None:
            self.children.add(child)

    def add_marriage(self, fid: str):
        """retrieve and add marriage information
        :param fid: the marriage fid
        """
        if not self.tree or not self.tree.fs:
            return

        if not self.fid:
            self.fid = fid
            url = "/platform/tree/couple-relationships/%s" % self.fid
            data = self.tree.fs.get_url(url)
            if data:
                if "facts" in data["relationships"][0]:
                    for x in data["relationships"][0]["facts"]:
                        self.facts.add(Fact(x, self.tree, num_prefix=f"FAM_{self.fid}"))
                if "sources" in data["relationships"][0]:
                    quotes = dict()
                    for x in data["relationships"][0]["sources"]:
                        quotes[x["descriptionId"]] = (
                            x["attribution"]["changeMessage"]
                            if "changeMessage" in x["attribution"]
                            else None
                        )
                    # self.tree.sources is effectively Dict[str, Source] so keys() returns strings
                    new_sources = quotes.keys() - self.tree.sources.keys()
                    if new_sources:
                        sources = self.tree.fs.get_url(
                            "/platform/tree/couple-relationships/%s/sources" % self.fid
                        )
                        for source in sources["sourceDescriptions"]:
                            if (
                                source["id"] in new_sources
                                and source["id"] not in self.tree.sources
                            ):
                                self.tree.sources[source["id"]] = Source(
                                    source, self.tree
                                )
                    for source_fid, change_message in quotes.items():
                        self.sources.add(
                            (self.tree.sources[source_fid], change_message)
                        )

    def get_notes(self):
        """retrieve marriage notes"""
        if self.fid and self.tree and self.tree.fs:
            notes = self.tree.fs.get_url(
                "/platform/tree/couple-relationships/%s/notes" % self.fid
            )
            if notes:
                for n in notes["relationships"][0]["notes"]:
                    text_note = "=== %s ===\n" % n["subject"] if "subject" in n else ""
                    text_note += n["text"] + "\n" if "text" in n else ""
                    self.notes.add(
                        Note(
                            text_note,
                            self.tree,
                            num_prefix=f"FAM_{self.fid}",
                            note_type="Marriage Note",
                        )
                    )

    @property
    def id(self):
        # Prefer fid (original FamilySearch ID) to preserve through merge
        # Fall back to num (counter) for newly created families
        return self.fid if self.fid else self.num

    def printxml(self, parent_element):
        # <family handle="_fa593c277af212e6c1f9f44bc4a" change="1720382301" id="F9MKP-K92">
        #   <rel type="Unknown"/>
        #   <father hlink="_fa593c277f14dc6db9ab19cbe09"/>
        #   <mother hlink="_fa593c277cd4af15983d7064c59"/>
        #   <childref hlink="_fa593c279e1466787c923487b98"/>
        #   <attribute type="_FSFTID" value="9MKP-K92"/>
        # </family>
        family = ET.SubElement(
            parent_element,
            "family",
            handle=self.handle,
            # change='1720382301',
            id=self.id,
        )
        ET.SubElement(family, "rel", type="Unknown")
        if self.husband:
            ET.SubElement(family, "father", hlink=self.husband.handle)
        if self.wife:
            ET.SubElement(family, "mother", hlink=self.wife.handle)
        for child in self.children:
            ET.SubElement(family, "childref", hlink=child.handle)
        for fact in self.facts:
            ET.SubElement(family, "eventref", hlink=fact.handle, role="Primary")

    def get_contributors(self):
        """retrieve contributors"""
        if self.fid and self.tree:
            url = "/platform/tree/couple-relationships/%s/changes" % self.fid
            text = self.tree.get_contributors_text(url)
            if text:
                for n in self.tree.notes:
                    if n.text == text:
                        self.notes.add(n)
                        return
                self.notes.add(Note(text, self.tree))

    def print(self, file=sys.stdout):
        """print family information in GEDCOM format"""
        file.write("0 @F%s@ FAM\n" % self.id)
        if self.husband:
            file.write("1 HUSB @I%s@\n" % self.husband.id)
        if self.wife:
            file.write("1 WIFE @I%s@\n" % self.wife.id)
        for child in sorted(self.children, key=lambda x: x.id or ""):
            file.write("1 CHIL @I%s@\n" % child.id)
        for fact in sorted(
            self.facts,
            key=lambda x: (
                x.date or "9999",
                x.type or "",
                x.value or "",
                x.place.id if x.place else "",
                x.note.text if x.note else "",
            ),
        ):
            fact.print(file)
        if self.sealing_spouse:
            file.write("1 SLGS\n")
            self.sealing_spouse.print(file)
        if self.fid:
            file.write("1 _FSFTID %s\n" % self.fid)
        for note in sorted(self.notes, key=lambda x: x.id or ""):
            note.link(file)
        for source, quote in sorted(
            self.sources, key=lambda x: (x[0].id or "", x[1] or "")
        ):
            source.link(file, 1)
            if quote:
                file.write(cont("2 PAGE " + quote))


class Tree:
    """family tree class
    :param fs: a Session object
    """

    def __init__(
        self,
        fs: Optional[GMASession] = None,
        exclude: Optional[List[str]] = None,
        geonames_key=None,
        creation_date: Optional[datetime] = None,
        **kwargs,
    ):
        self.fs = fs
        self.geonames_key = geonames_key
        self.lock = threading.Lock()
        self.creation_date: Optional[datetime] = creation_date
        self.indi: Dict[str, Indi] = {}
        self.fam: Dict[str, Fam] = {}
        self.notes: Set[Note] = set()
        self.facts: Set[Fact] = set()
        self.sources: Dict[str, Source] = {}
        self.citations: Dict[str, Citation] = {}
        self.places: Set[Place] = set()
        self.places_by_names: Dict[str, Place] = {}
        self.place_cache: Dict[str, Tuple[float, float]] = {}
        self.display_name: Optional[str] = None
        self.lang: Optional[str] = None
        self.exclude: List[str] = exclude or []
        self.only_blood_relatives = False
        if "only_blood_relatives" in kwargs:
            self.only_blood_relatives = kwargs["only_blood_relatives"]
        self.place_counter = 0
        if fs:
            self.display_name = fs.display_name
            self.lang = babelfish.Language.fromalpha2(fs.lang).name

        # Geocoder cache - honor GMA_CACHE_DIR if present, else fallback to ~/.cache/getmyancestors/
        geocache_dir = os.environ.get(
            "GMA_CACHE_DIR", os.path.expanduser("~/.cache/getmyancestors")
        )
        os.makedirs(geocache_dir, exist_ok=True)
        geocache_path = os.path.join(geocache_dir, "geocoder_requests")

        self.geosession = CachedSession(
            geocache_path,
            backend="sqlite",
            expire_after=86400,
            allowable_codes=(200,),
            backend_kwargs={"table_name": "requests"},
        )
        if os.environ.get("GMA_OFFLINE_MODE"):
            orig_request = self.geosession.request

            def offline_request(*args, **kwargs):
                kwargs["only_if_cached"] = True
                return orig_request(*args, **kwargs)

            self.geosession.request = offline_request  # type: ignore[method-assign]

    def add_indis(self, fids_in: Iterable[str]):
        """add individuals to the family tree
        :param fids: an iterable of fid
        """
        fids = []
        for fid in fids_in:
            if fid not in self.exclude:
                fids.append(fid)
            else:
                print("Excluding %s from the family tree" % fid, file=sys.stderr)

        async def add_datas(loop, data):
            futures = set()
            for person in data["persons"]:
                self.indi[person["id"]] = Indi(person["id"], self)
                futures.add(
                    loop.run_in_executor(None, self.indi[person["id"]].add_data, person)
                )
            for future in futures:
                await future

        new_fids = sorted([fid for fid in fids if fid and fid not in self.indi])
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while new_fids:
            if not self.fs:
                break
            data = self.fs.get_url(
                "/platform/tree/persons?pids=" + ",".join(new_fids[:MAX_PERSONS])
            )
            if data:
                if "places" in data:
                    for place in data["places"]:
                        if place["id"] not in self.place_cache:
                            self.place_cache[place["id"]] = (
                                place["latitude"],
                                place["longitude"],
                            )
                loop.run_until_complete(add_datas(loop, data))
                if "childAndParentsRelationships" in data:
                    for rel in data["childAndParentsRelationships"]:
                        father: str | None = rel.get("parent1", {}).get("resourceId")
                        mother: str | None = rel.get("parent2", {}).get("resourceId")
                        child: str | None = rel.get("child", {}).get("resourceId")

                        # Extract relationship types from fatherFacts/motherFacts
                        father_rel = None
                        mother_rel = None
                        for fact in rel.get("fatherFacts", []):
                            if "type" in fact:
                                father_rel = ParentRelType.from_fs_type(fact["type"])
                                break
                        for fact in rel.get("motherFacts", []):
                            if "type" in fact:
                                mother_rel = ParentRelType.from_fs_type(fact["type"])
                                break

                        # Store parent relationship with types
                        if child in self.indi:
                            self.indi[child].parents.add(
                                (father, mother, father_rel, mother_rel)
                            )
                        if father in self.indi:
                            self.indi[father].children.add((father, mother, child))
                        if mother in self.indi:
                            self.indi[mother].children.add((father, mother, child))
                if "relationships" in data:
                    for rel in data["relationships"]:
                        if rel["type"] == "http://gedcomx.org/Couple":
                            person1 = rel["person1"]["resourceId"]
                            person2 = rel["person2"]["resourceId"]
                            relfid = rel["id"]
                            if person1 in self.indi:
                                self.indi[person1].spouses.add(
                                    (person1, person2, relfid)
                                )
                            if person2 in self.indi:
                                self.indi[person2].spouses.add(
                                    (person1, person2, relfid)
                                )
            new_fids = new_fids[MAX_PERSONS:]

    def ensure_source(self, source_data: Dict[str, Any]) -> Source:
        with self.lock:
            if source_data["id"] not in self.sources:
                self.sources[source_data["id"]] = Source(source_data, self)
            return self.sources[source_data["id"]]

    def ensure_citation(self, data: Dict[str, Any], source: Source) -> Citation:
        with self.lock:
            citation_id = data["id"]
            if citation_id not in self.citations:
                self.citations[citation_id] = Citation(data, source)
            return self.citations[citation_id]

    def ensure_family(self, father: Optional["Indi"], mother: Optional["Indi"]) -> Fam:
        with self.lock:
            fam_id = Fam.gen_id(father, mother)
            if fam_id not in self.fam:
                self.fam[fam_id] = Fam(father, mother, self)
            return self.fam[fam_id]

    def get_contributors_text(self, url: str) -> Optional[str]:
        """Helper to fetch contributors from a changelog URL"""
        if not self.fs:
            return None
        data = self.fs.get_url(url, {"Accept": "application/x-gedcomx-atom+json"})
        if not data:
            return None

        contributors_map = {}  # name -> uri
        names = set()

        for entry in data.get("entries", []):
            for contrib in entry.get("contributors", []):
                name = contrib.get("name", "Unknown")
                uri = contrib.get("uri", "").replace("https://www.familysearch.org", "")
                contributors_map[name] = uri
                names.add(name)

        if not names:
            return None

        text = "=== %s ===\n" % self.fs._("Contributors")

        for name in sorted(names):
            text += name
            agent_uri = contributors_map[name]
            # Fetch agent details
            # Default headers work better per jcarroll findings
            agent_data = self.fs.get_url(agent_uri)

            # Display Name
            try:
                agent_names = agent_data["agents"][0]["names"]
                display_name = "".join([n["value"] + " " for n in agent_names]).strip()
                if display_name != name:
                    text += " (" + display_name + ")"
            except (KeyError, IndexError, TypeError):
                pass

            # Email
            try:
                email = agent_data["agents"][0]["emails"][0]["resource"].replace(
                    "mailto:", " "
                )
                text += email
            except (KeyError, IndexError, TypeError):
                pass

            # Phone
            try:
                phone = agent_data["agents"][0]["phones"][0]["resource"].replace(
                    "tel:", " "
                )
                text += phone
            except (KeyError, IndexError, TypeError):
                pass

            text += "\n"

        return text

    def place_by_geoname_id(self, place_id: str) -> Optional[Place]:
        for place in self.places:
            if place.id == place_id:
                return place
        return None

    def get_by_geonames_id(self, geonames_id: str) -> Optional[Place]:
        print("Fetching place hierarchy for", geonames_id, file=sys.stderr)
        hierarchy = geocoder.geonames(
            geonames_id,
            key=self.geonames_key,
            lang=["hu", "en", "de"],
            method="hierarchy",
            session=self.geosession,
        )

        if hierarchy and hierarchy.ok:
            last_place = None
            for item in hierarchy.geojson.get("features", []):
                properties = item.get("properties", {})
                code = properties.get("code")

                if code in ["AREA", "CONT"]:
                    continue

                print("Properties", properties, file=sys.stderr)
                place_id = "GEO" + str(properties["geonames_id"])
                place = self.place_by_geoname_id(place_id)
                if place is None:
                    place = Place(
                        place_id,
                        properties.get("address"),
                        GEONAME_FEATURE_MAP.get(code, "Unknown"),
                        last_place,
                        properties.get("lat"),
                        properties.get("lng"),
                    )
                    self.places.add(place)
                last_place = place
            return last_place
        return None

    @property
    def _next_place_counter(self):
        self.place_counter += 1
        return self.place_counter

    def ensure_place(
        self,
        place_name: str,
        fid: Optional[str] = None,
        coord: Optional[Tuple[float, float]] = None,
    ) -> Place:
        with self.lock:
            if place_name not in self.places_by_names:
                place = None
                if self.geonames_key:
                    print("Fetching place", place_name, file=sys.stderr)
                    geoname_record = geocoder.geonames(
                        place_name,
                        key=self.geonames_key,
                        session=self.geosession,
                    )
                    if geoname_record and geoname_record.ok:
                        place = self.get_by_geonames_id(geoname_record.geonames_id)
                if place is None:
                    coord = (
                        self.place_cache.get(fid) if coord is None and fid else coord
                    )
                    start_char = (
                        "P"
                        + hashlib.md5(place_name.encode("utf-8"))
                        .hexdigest()[:6]
                        .upper()
                    )
                    place = Place(
                        ("PFSID" + fid if fid is not None else start_char),
                        place_name,
                        latitude=coord[0] if coord is not None else None,
                        longitude=coord[1] if coord is not None else None,
                    )
                    self.places.add(place)
                self.places_by_names[place_name] = place
            return self.places_by_names[place_name]

    # def add_fam(self, father, mother):
    #     """add a family to the family tree
    #     :param father: the father fid or None
    #     :param mother: the mother fid or None
    #     """
    #     if (father, mother) not in self.fam:
    #         self.fam[(father, mother)] = Fam(father, mother, self)

    def add_trio(
        self,
        father: Indi | None,
        mother: Indi | None,
        child: Indi | None,
        father_rel: Optional[ParentRelType] = None,
        mother_rel: Optional[ParentRelType] = None,
    ):
        """add a children relationship to the family tree
        :param father: the father Indi or None
        :param mother: the mother Indi or None
        :param child: the child Indi or None
        :param father_rel: relationship type to father (birth, step, adopted, foster)
        :param mother_rel: relationship type to mother (birth, step, adopted, foster)
        """
        fam = self.ensure_family(father, mother)
        if child is not None:
            fam.add_child(child)
            # Use the more specific relationship type (default to birth if both are the same)
            rel_type = father_rel or mother_rel
            child.add_famc(fam, rel_type)

        if father is not None:
            father.add_fams(fam)
        if mother is not None:
            mother.add_fams(fam)

    def add_parents(self, fids: Iterable[str]) -> Set[str]:
        """add parents relationships
        :param fids: a set of fids
        """
        # Materialize once to avoid exhausting iterator
        fids_list = [f for f in fids if f in self.indi]
        parents = set()
        for fid in fids_list:
            for father, mother, _, _ in self.indi[fid].parents:
                if father:
                    parents.add(father)
                if mother:
                    parents.add(mother)
        if parents:
            parents -= set(self.exclude)
            self.add_indis(set(filter(None, parents)))
        for fid in fids_list:
            for father, mother, father_rel, mother_rel in self.indi[fid].parents:
                self.add_trio(
                    self.indi.get(father) if father else None,
                    self.indi.get(mother) if mother else None,
                    self.indi.get(fid) if fid else None,
                    father_rel,
                    mother_rel,
                )
        return parents

    def add_spouses(self, fids: Iterable[str]):
        """add spouse relationships
        :param fids: a set of fid
        """

        async def add(
            loop, rels: Set[Tuple[Optional[str], Optional[str], Optional[str]]]
        ):
            futures = set()
            for father, mother, relfid in rels:
                if (
                    father in self.exclude
                    or mother in self.exclude
                    or not father
                    or not mother
                ):
                    continue
                fam_id = Fam.gen_id(self.indi[father], self.indi[mother])
                if self.fam.get(fam_id):
                    futures.add(
                        loop.run_in_executor(
                            None, self.fam[fam_id].add_marriage, relfid
                        )
                    )
            for future in futures:
                await future

        rels: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()
        for fid in [f for f in fids if f in self.indi]:
            rels |= self.indi[fid].spouses
        # TODO: test this
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if rels:
            all_involved = set.union(
                set(),
                *(
                    {father, mother}
                    for father, mother, relfid in rels
                    if father and mother
                ),
            )
            self.add_indis(set(filter(None, all_involved)))
            for father, mother, _ in rels:
                if father in self.indi and mother in self.indi:
                    father_indi = self.indi[father]
                    mother_indi = self.indi[mother]
                    fam = self.ensure_family(father_indi, mother_indi)
                    father_indi.add_fams(fam)
                    mother_indi.add_fams(fam)

            loop.run_until_complete(add(loop, rels))

    def add_children(self, fids: Iterable[str]) -> Set[str]:
        """add children relationships
        :param fids: a set of fid
        """
        rels: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()
        for fid in [f for f in fids if f in self.indi]:
            rels |= self.indi[fid].children if fid in self.indi else set()
        children = set()
        if rels:
            all_involved = set.union(set(), *(set(rel) for rel in rels if rel))
            all_involved -= set(self.exclude)
            self.add_indis(set(filter(None, all_involved)))
            for father, mother, child in rels:
                has_child = child in self.indi
                if not has_child:
                    continue

                father_valid = not father or father in self.indi
                mother_valid = not mother or mother in self.indi
                if father_valid and mother_valid and (father or mother):
                    self.add_trio(
                        self.indi.get(father) if father else None,
                        self.indi.get(mother) if mother else None,
                        self.indi.get(child) if child else None,
                    )
                    children.add(child)
        return set(filter(None, children))

    def add_ordinances(self, fid):
        """retrieve ordinances
        :param fid: an individual fid
        """
        if fid in self.indi:
            ret, famc = self.indi[fid].get_ordinances()
            if famc:
                # self.fam is keyed by (father_id, mother_id), so we can't look up by fam_id directly.
                # Find family by iterating values
                for f in self.fam.values():
                    if f.fid == famc:
                        sc = self.indi[fid].sealing_child
                        if sc:
                            sc.famc = f
                        break
            for o in ret:
                spouse_id = o["relationships"]["spouseId"]
                for f in self.fam.values():
                    if (
                        f.husband
                        and f.husband.fid == fid
                        and f.wife
                        and f.wife.fid == spouse_id
                    ):
                        f.sealing_spouse = Ordinance(o)
                        break
                    if (
                        f.husband
                        and f.husband.fid == spouse_id
                        and f.wife
                        and f.wife.fid == fid
                    ):
                        f.sealing_spouse = Ordinance(o)
                        break

    def reset_num(self):
        """reset all GEDCOM identifiers"""
        # TODO: implement this
        # for husb, wife in self.fam:
        #     self.fam[(husb, wife)].husb_num = self.indi[husb].num if husb else None
        #     self.fam[(husb, wife)].wife_num = self.indi[wife].num if wife else None
        #     self.fam[(husb, wife)].chil_num = set(
        #         self.indi[chil].num for chil in self.fam[(husb, wife)].chil_fid
        #     )
        # for fid in self.indi:
        #     self.indi[fid].famc_num = set(
        #         self.fam[(husb, wife)].num for husb, wife in self.indi[fid].famc_fid
        #     )
        #     self.indi[fid].fams_num = set(
        #         self.fam[(husb, wife)].num for husb, wife in self.indi[fid].fams_fid
        #     )
        #     self.indi[fid].famc_ids = set(
        #         self.fam[(husb, wife)].id for husb, wife in self.indi[fid].famc_fid
        #     )
        #     self.indi[fid].fams_ids = set(
        #         self.fam[(husb, wife)].id for husb, wife in self.indi[fid].fams_fid
        #     )

    def printxml(self, file: BinaryIO):
        # TODO: implement this
        #         root = ET.Element("root")
        #         doc = ET.SubElement(root, "doc")

        #         ET.SubElement(doc, "field1", name="blah").text = "some value1"
        #         ET.SubElement(doc, "field2", name="asdfasd").text = "some vlaue2"

        #         tree = ET.ElementTree(root)
        #         tree.write("filename.xml")

        #         <?xml version="1.0" encoding="UTF-8"?>
        # <!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
        # "http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
        # <database xmlns="http://gramps-project.org/xml/1.7.1/">
        #   <header
        #     <created date="2024-07-07" version="5.2.2"/>
        #     <researcher>
        #       <resname>Barnabás Südy</resname>
        #     </researcher>
        #   </header>

        root = ET.Element("database", xmlns="http://gramps-project.org/xml/1.7.1/")

        header = ET.SubElement(root, "header")
        ET.SubElement(
            header,
            "created",
            date=datetime.strftime(datetime.now(), "%Y-%m-%d"),
            version="5.2.2",
        )
        researcher = ET.SubElement(header, "researcher")
        resname = ET.SubElement(researcher, "resname")
        resname.text = self.display_name

        people = ET.SubElement(root, "people")
        for indi in sorted(self.indi.values(), key=lambda x: str(x.id or "")):
            indi.printxml(people)

        families = ET.SubElement(root, "families")
        for fam in sorted(self.fam.values(), key=lambda x: str(x.id or "")):
            fam.printxml(families)

        events = ET.SubElement(root, "events")
        for fact in self.facts:
            fact.printxml(events)

        notes = ET.SubElement(root, "notes")
        for note in sorted(self.notes, key=lambda x: x.id):
            note.printxml(notes)

        places = ET.SubElement(root, "places")
        for place in self.places:
            place.printxml(places)

        sources = ET.SubElement(root, "sources")
        for source in self.sources.values():
            source.printxml(sources)

        citations = ET.SubElement(root, "citations")
        for citation in self.citations.values():
            citation.printxml(citations)

        tree = ET.ElementTree(root)

        doctype = '<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN" "http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'
        file.write(doctype.encode("utf-8"))
        tree.write(file, "utf-8")

    def print(self, file=sys.stdout):
        """print family tree in GEDCOM format"""
        file.write("0 HEAD\n")
        file.write("1 CHAR UTF-8\n")
        file.write("1 GEDC\n")
        file.write("2 VERS 5.5.1\n")
        file.write("2 FORM LINEAGE-LINKED\n")
        file.write("1 SOUR getmyancestors\n")
        file.write("2 VERS %s\n" % __version__)
        file.write("2 NAME getmyancestors\n")
        # Use provided creation date if available, otherwise current time
        if self.creation_date:
            date_str = self.creation_date.strftime("%d %b %Y").upper()
            time_str = self.creation_date.strftime("%H:%M:%S")
        else:
            date_str = time.strftime("%d %b %Y").upper()
            time_str = time.strftime("%H:%M:%S")

        file.write("1 DATE %s\n" % date_str)
        file.write("2 TIME %s\n" % time_str)
        file.write("1 SUBM @SUBM@\n")
        file.write("0 @SUBM@ SUBM\n")
        file.write("1 NAME %s\n" % self.display_name)
        # file.write("1 LANG %s\n" % self.lang)

        for fid in sorted(self.indi, key=lambda x: self.indi[x].id or ""):
            self.indi[fid].print(file)
        for fam in sorted(self.fam.values(), key=lambda x: x.id or ""):
            fam.print(file)
        sources = sorted(self.sources.values(), key=lambda x: x.id or "")
        for s in sources:
            s.print(file)
        # Deduplicate notes by text content before printing
        seen_texts = set()
        unique_notes = []
        for n in sorted(self.notes, key=lambda x: x.id):
            if n.text not in seen_texts:
                seen_texts.add(n.text)
                unique_notes.append(n)
        for n in unique_notes:
            n.print(file)
        file.write("0 TRLR\n")
