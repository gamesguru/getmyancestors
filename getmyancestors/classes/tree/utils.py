"""Utility constants and functions for tree package"""

import os
import re
import sys


def warn(msg: str):
    """Write a warning message to stderr with optional color (if TTY)."""
    use_color = sys.stderr.isatty() or os.environ.get("FORCE_COLOR", "")
    if use_color:
        sys.stderr.write(f"\033[1;33m{msg}\033[0m\n")  # Bold yellow
    else:
        sys.stderr.write(f"{msg}\n")


# Constants
COUNTY = "County"
COUNTRY = "Country"
CITY = "City"


NAME_MAP = {
    "preferred": "Preferred Name",
    "nickname": "Nickname",
    "birthname": "Birth Name",
    "aka": "Also Known As",
    "married": "Married Name",
}


GEONAME_FEATURE_MAP = {
    "ADM1": COUNTY,  # 	first-order administrative division	a primary administrative division of a country, such as a state in the United States
    "ADM1H": COUNTY,  #  historical first-order administrative division	a former first-order administrative division
    "ADM2": COUNTY,  # 	second-order administrative division	a subdivision of a first-order administrative division
    "ADM2H": COUNTY,  # 	historical second-order administrative division	a former second-order administrative division
    "ADM3": COUNTY,  # 	third-order administrative division	a subdivision of a second-order administrative division
    "ADM3H": COUNTY,  # 	historical third-order administrative division	a former third-order administrative division
    "ADM4": COUNTY,  # 	fourth-order administrative division	a subdivision of a third-order administrative division
    "ADM4H": COUNTY,  # 	historical fourth-order administrative division	a former fourth-order administrative division
    "ADM5": COUNTY,  # 	fifth-order administrative division	a subdivision of a fourth-order administrative division
    "ADM5H": COUNTY,  # 	historical fifth-order administrative division	a former fifth-order administrative division
    "ADMD": COUNTY,  # 	administrative division	an administrative division of a country, undifferentiated as to administrative level
    "ADMDH": COUNTY,  # 	historical administrative division 	a former administrative division of a political entity, undifferentiated as to administrative level
    # 'LTER': 	leased area	a tract of land leased to another country, usually for military installations
    "PCL": COUNTRY,  # political entity
    "PCLD": COUNTRY,  # dependent political entity
    "PCLF": COUNTRY,  # freely associated state
    "PCLH": COUNTRY,  # historical political entity	a former political entity
    "PCLI": COUNTRY,  # independent political entity
    "PCLIX": COUNTRY,  # section of independent political entity
    "PCLS": COUNTRY,  # semi-independent political entity
    "PPL": CITY,  # populated place	a city, town, village, or other agglomeration of buildings where people live and work
    "PPLA": CITY,  # seat of a first-order administrative division	seat of a first-order administrative division (PPLC takes precedence over PPLA)
    "PPLA2": CITY,  # seat of a second-order administrative division
    "PPLA3": CITY,  # seat of a third-order administrative division
    "PPLA4": CITY,  # seat of a fourth-order administrative division
    "PPLA5": CITY,  # seat of a fifth-order administrative division
    "PPLC": CITY,  # capital of a political entity
    "PPLCH": CITY,  # historical capital of a political entity	a former capital of a political entity
    "PPLF": CITY,  # farm village	a populated place where the population is largely engaged in agricultural activities
    "PPLG": CITY,  # seat of government of a political entity
    "PPLH": CITY,  # historical populated place	a populated place that no longer exists
    "PPLL": CITY,  # populated locality	an area similar to a locality but with a small group of dwellings or other buildings
    "PPLQ": CITY,  # abandoned populated place
    "PPLR": CITY,  # religious populated place	a populated place whose population is largely engaged in religious occupations
    "PPLS": CITY,  # populated places	cities, towns, villages, or other agglomerations of buildings where people live and work
    "PPLW": CITY,  # destroyed populated place	a village, town or city destroyed by a natural disaster, or by war
    "PPLX": CITY,  # section of populated place
}


def cont(string):
    """parse a GEDCOM line adding CONT and CONT tags if necessary"""
    level = int(string[:1]) + 1
    lines = string.splitlines()
    res = []
    max_len = 255
    for line in lines:
        c_line = line
        to_conc = []
        while len(c_line.encode("utf-8")) > max_len:
            index = min(max_len, len(c_line) - 2)
            while (
                len(c_line[:index].encode("utf-8")) > max_len
                or re.search(r"[ \t\v]", c_line[index - 1 : index + 1])
            ) and index > 1:
                index -= 1
            to_conc.append(c_line[:index])
            c_line = c_line[index:]
            max_len = 248
        to_conc.append(c_line)
        res.append(("\n%s CONC " % level).join(to_conc))
        max_len = 248
    return ("\n%s CONT " % level).join(res) + "\n"
