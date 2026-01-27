"""Tree module for family tree data structures"""

# Import classes in dependency order (utils -> records -> elements -> core)
from .core import Fam, Indi, Tree
from .elements import Citation, Name, Ordinance, Place
from .records import Fact, Memorie, Note, Source
from .utils import CITY, COUNTRY, COUNTY, GEONAME_FEATURE_MAP, NAME_MAP, cont

__all__ = [
    # Functions
    "cont",
    # Constants
    "COUNTY",
    "COUNTRY",
    "CITY",
    "NAME_MAP",
    "GEONAME_FEATURE_MAP",
    # Classes from records
    "Note",
    "Source",
    "Fact",
    "Memorie",
    # Classes from elements
    "Name",
    "Place",
    "Ordinance",
    "Citation",
    # Classes from core
    "Indi",
    "Fam",
    "Tree",
]
