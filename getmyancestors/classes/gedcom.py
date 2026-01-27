from typing import Optional

from getmyancestors.classes.constants import FACT_TYPES, ORDINANCES
from getmyancestors.classes.tree import (
    Fact,
    Fam,
    Indi,
    Memorie,
    Name,
    Note,
    Ordinance,
    Source,
)
from getmyancestors.utils import _error, _warn


class Gedcom:
    """Parse a GEDCOM file into a Tree"""

    def __init__(self, file, tree):
        self.f = file
        self.num = None
        self.tree = tree
        self.level = 0
        self.pointer = None
        self.tag: Optional[str] = None
        self.data: Optional[str] = None
        self.flag = False
        self.indi = dict()
        self.fam = dict()
        self.note = dict()
        self.sour = dict()
        self.__parse()
        self.__add_id()

    def __parse(self):
        """Parse the GEDCOM file into self.tree"""
        while self.__get_line():
            if self.tag == "INDI" and self.pointer:
                self.num = self.pointer[2 : len(self.pointer) - 1]
                self.indi[self.num] = Indi(tree=self.tree, num=self.num)
                self.__get_indi()
            elif self.tag == "FAM" and self.pointer:
                self.num = self.pointer[2 : len(self.pointer) - 1]
                if self.num not in self.fam:
                    self.fam[self.num] = Fam(tree=self.tree, num=self.num)
                self.__get_fam()
            elif self.tag == "NOTE" and self.pointer:
                self.num = self.pointer[2 : len(self.pointer) - 1]
                if self.num not in self.note:
                    self.note[self.num] = Note(tree=self.tree, num=self.num)
                self.__get_note()
            elif self.tag == "SOUR" and self.pointer:
                self.num = self.pointer[2 : len(self.pointer) - 1]
                if self.num not in self.sour:
                    self.sour[self.num] = Source(num=self.num)
                self.__get_source()
            elif self.tag == "SUBM" and self.pointer:
                self.__get_subm()

    def __get_subm(self):
        while self.__get_line() and self.level > 0:
            if not self.tree.display_name or not self.tree.lang:
                if self.tag == "NAME":
                    self.tree.display_name = self.data
                elif self.tag == "LANG":
                    self.tree.lang = self.data
        self.flag = True

    def __get_line(self):
        """Parse a new line
        If the flag is set, skip reading a newline
        """
        if self.flag:
            self.flag = False
            return True
        words = self.f.readline().split()

        if not words:
            return False
        self.level = int(words[0])
        if words[1][0] == "@":
            self.pointer = words[1]
            self.tag = words[2]
            self.data = " ".join(words[3:])
        else:
            self.pointer = None
            self.tag = words[1]
            self.data = " ".join(words[2:])
        return True

    def __get_indi(self):
        """Parse an individual"""
        while self.f and self.__get_line() and self.level > 0:
            if self.tag == "NAME":
                self.__get_name()
            elif self.tag == "SEX":
                self.indi[self.num].gender = self.data
            elif self.tag in FACT_TYPES or self.tag == "EVEN":
                self.indi[self.num].facts.add(self.__get_fact())
            elif self.tag == "BAPL":
                self.indi[self.num].baptism = self.__get_ordinance()
            elif self.tag == "CONL":
                self.indi[self.num].confirmation = self.__get_ordinance()
            elif self.tag == "WAC":
                self.indi[self.num].initiatory = self.__get_ordinance()
            elif self.tag == "ENDL":
                self.indi[self.num].endowment = self.__get_ordinance()
            elif self.tag == "SLGC":
                self.indi[self.num].sealing_child = self.__get_ordinance()
            elif self.tag == "FAMS":
                if self.data:
                    self.indi[self.num].fams_num.add(self.data[2 : len(self.data) - 1])
            elif self.tag == "FAMC":
                if self.data:
                    self.indi[self.num].famc_num.add(self.data[2 : len(self.data) - 1])
            elif self.tag == "_FSFTID":
                self.indi[self.num].fid = self.data
            elif self.tag == "NOTE":
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.note:
                        self.note[num] = Note(tree=self.tree, num=num)
                    self.indi[self.num].notes.add(self.note[num])
            elif self.tag == "SOUR":
                self.indi[self.num].sources.add(self.__get_link_source())
            elif self.tag == "OBJE":
                self.indi[self.num].memories.add(self.__get_memorie())
        self.flag = True

    def __get_fam(self):
        """Parse a family"""
        while self.__get_line() and self.level > 0:
            if self.tag == "HUSB":
                if self.data:
                    self.fam[self.num].husb_num = self.data[2 : len(self.data) - 1]
            elif self.tag == "WIFE":
                if self.data:
                    self.fam[self.num].wife_num = self.data[2 : len(self.data) - 1]
            elif self.tag == "CHIL":
                if self.data:
                    self.fam[self.num].chil_num.add(self.data[2 : len(self.data) - 1])
            elif self.tag in FACT_TYPES:
                self.fam[self.num].facts.add(self.__get_fact())
            elif self.tag == "SLGS":
                self.fam[self.num].sealing_spouse = self.__get_ordinance()
            elif self.tag == "_FSFTID":
                self.fam[self.num].fid = self.data
            elif self.tag == "NOTE":
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.note:
                        self.note[num] = Note(tree=self.tree, num=num)
                    self.fam[self.num].notes.add(self.note[num])
            elif self.tag == "SOUR":
                self.fam[self.num].sources.add(self.__get_link_source())
        self.flag = True

    def __get_name(self):
        """Parse a name"""
        parts = self.__get_text().split("/")
        name = Name()
        added = False
        name.given = parts[0].strip()
        name.surname = parts[1].strip()
        if parts[2]:
            name.suffix = parts[2]
        if not self.indi[self.num].name:
            self.indi[self.num].name = name
            added = True
        while self.__get_line() and self.level > 1:
            if self.tag == "NPFX":
                name.prefix = self.data
            elif self.tag == "TYPE":
                if self.data == "aka":
                    self.indi[self.num].aka.add(name)
                    added = True
                elif self.data == "married":
                    self.indi[self.num].married.add(name)
                    added = True
            elif self.tag == "NICK":
                nick = Name()
                nick.given = self.data or ""
                self.indi[self.num].nicknames.add(nick)
            elif self.tag == "NOTE":
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.note:
                        self.note[num] = Note(tree=self.tree, num=num)
                    name.note = self.note[num]
        if not added:
            self.indi[self.num].birthnames.add(name)
        self.flag = True

    def __get_fact(self):
        """Parse a fact"""
        fact = Fact()
        if self.tag != "EVEN":
            fact.type = FACT_TYPES[self.tag]
            fact.value = self.data
        while self.__get_line() and self.level > 1:
            if self.tag == "TYPE":
                fact.type = self.data
            if self.tag == "DATE":
                fact.date = self.__get_text()
            elif self.tag == "PLAC":
                fact.place = self.tree.ensure_place(self.__get_text())
            elif self.tag == "MAP":
                fact.map = self.__get_map()
            elif self.tag == "NOTE":
                if self.data and self.data[:12] == "Description:":
                    fact.value = self.data[13:]
                    continue
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.note:
                        self.note[num] = Note(tree=self.tree, num=num)
                    fact.note = self.note[num]
            elif self.tag == "CONT":
                fact.value = (fact.value or "") + "\n" + (self.data or "")
            elif self.tag == "CONC":
                fact.value = (fact.value or "") + (self.data or "")
        self.flag = True
        return fact

    def __get_map(self):
        """Parse map coordinates"""
        latitude = None
        longitude = None
        while self.__get_line() and self.level > 3:
            if self.tag == "LATI":
                latitude = self.data
            elif self.tag == "LONG":
                longitude = self.data
        self.flag = True
        return (latitude, longitude)

    def __get_text(self):
        """Parse a multiline text"""
        text = self.data or ""
        while self.__get_line():
            if self.tag == "CONT":
                text += "\n" + (self.data if self.data else "")
            elif self.tag == "CONC":
                text += self.data if self.data else ""
            else:
                break
        self.flag = True
        return text

    def __get_source(self):
        """Parse a source"""
        while self.__get_line() and self.level > 0:
            if self.tag == "TITL":
                self.sour[self.num].title = self.__get_text()
            elif self.tag == "AUTH":
                self.sour[self.num].citation = self.__get_text()
            elif self.tag == "PUBL":
                self.sour[self.num].url = self.__get_text()
            elif self.tag == "REFN":
                self.sour[self.num].fid = self.data
                if self.data in self.tree.sources:
                    self.sour[self.num] = self.tree.sources[self.data]
                else:
                    self.tree.sources[self.data] = self.sour[self.num]
            elif self.tag == "NOTE":
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.note:
                        self.note[num] = Note(tree=self.tree, num=num)
                    self.sour[self.num].notes.add(self.note[num])
        self.flag = True

    def __get_link_source(self):
        """Parse a link to a source"""
        num = "0"
        if self.data:
            num = self.data[2 : len(self.data) - 1]

        if num not in self.sour:
            self.sour[num] = Source(num=num)
        page = None
        while self.__get_line() and self.level > 1:
            if self.tag == "PAGE":
                page = self.__get_text()
        self.flag = True
        return (self.sour[num], page)

    def __get_memorie(self):
        """Parse a memorie"""
        memorie = Memorie()
        while self.__get_line() and self.level > 1:
            if self.tag == "TITL":
                memorie.description = self.__get_text()
            elif self.tag == "FILE":
                memorie.url = self.__get_text()
        self.flag = True
        return memorie

    def __get_note(self):
        """Parse a note"""
        self.note[self.num].text = self.__get_text()
        self.flag = True

    def __get_ordinance(self):
        """Parse an ordinance"""
        ordinance = Ordinance()
        while self.__get_line() and self.level > 1:
            if self.tag == "DATE":
                ordinance.date = self.__get_text()
            elif self.tag == "TEMP":
                ordinance.temple_code = self.data
            elif self.tag == "STAT":
                ordinance.status = ORDINANCES[self.data]
            elif self.tag == "FAMC":
                if self.data:
                    num = self.data[2 : len(self.data) - 1]
                    if num not in self.fam:
                        self.fam[num] = Fam(tree=self.tree, num=num)
                    ordinance.famc = self.fam[num]
        self.flag = True
        return ordinance

    def __add_id(self):
        """Reset GEDCOM identifiers"""
        # Set fallback fid from GEDCOM pointer if _FSFTID was not present
        for num, indi in self.indi.items():
            if indi.fid is None:
                name_str = str(indi.name) if indi.name else "Unknown"
                _warn(
                    f"Warning: Individual @I{num}@ ({name_str}) missing _FSFTID tag, "
                    f"using GEDCOM pointer as fallback."
                )
                indi.fid = num  # Use GEDCOM pointer ID as fallback

        for num, fam in self.fam.items():
            if fam.fid is None:
                husb_name = "Unknown"
                if fam.husb_num and fam.husb_num in self.indi:
                    h = self.indi[fam.husb_num]
                    husb_name = str(h.name) if h.name else "Unknown"

                wife_name = "Unknown"
                if fam.wife_num and fam.wife_num in self.indi:
                    w = self.indi[fam.wife_num]
                    wife_name = str(w.name) if w.name else "Unknown"

                _warn(
                    f"Warning: Family @F{num}@ ({husb_name} & {wife_name}) missing _FSFTID tag, "
                    f"using GEDCOM pointer as fallback."
                )
                if husb_name != "Unknown" and wife_name != "Unknown":
                    _error(
                        f"Error: Family @F{num}@ ({husb_name} & {wife_name}) has NO _FSFTID tag! "
                        "This may imply a problem with the FamilySearch data. You may need to investigate it."
                    )
                fam.fid = num  # Use GEDCOM pointer ID as fallback

        for _num, fam in self.fam.items():
            if fam.husb_num:
                fam.husb_fid = self.indi[fam.husb_num].fid
            if fam.wife_num:
                fam.wife_fid = self.indi[fam.wife_num].fid
            for chil in fam.chil_num:
                fam.chil_fid.add(self.indi[chil].fid)
        for _num, indi in self.indi.items():
            for famc in indi.famc_num:
                # Store fam.fid instead of (husb, wife) tuple for consistent keying
                indi.famc_fid.add(self.fam[famc].fid)
            for fams in indi.fams_num:
                indi.fams_fid.add(self.fam[fams].fid)
