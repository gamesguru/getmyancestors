

from getmyancestors.classes.tree.core import Indi, Tree


def test_indi_name_population(mock_session):
    """
    Test that Indi.add_data correctly populates self.name when a preferred name is present.
    """
    tree = Tree(fs=mock_session)
    indi = Indi(fid="INDI123", tree=tree)

    data = {
        "living": False,
        "names": [
            {
                "type": "http://gedcomx.org/BirthName",
                "preferred": True,
                "nameForms": [
                    {
                        "parts": [
                            {"type": "http://gedcomx.org/Given", "value": "John"},
                            {"type": "http://gedcomx.org/Surname", "value": "Doe"},
                        ]
                    }
                ],
            },
            {
                "type": "http://gedcomx.org/Nickname",
                "preferred": False,
                "nameForms": [
                    {"parts": [{"type": "http://gedcomx.org/Given", "value": "Johnny"}]}
                ],
            },
        ],
    }

    indi.add_data(data)

    assert indi.name is not None
    assert indi.name.given == "John"
    assert indi.name.surname == "Doe"
    assert indi.name.kind == "birthname"

    # Verify other names are still added
    assert len(indi.nicknames) == 1
    nickname = list(indi.nicknames)[0]
    assert nickname.given == "Johnny"


def test_indi_name_population_no_preferred(mock_session):
    """
    Test fallback behavior or at least ensure no crash if no preferred name (though typically FS provides one).
    Logic dictates self.name might remain None or be set if logic allows (current logic only sets if not alt).
    """
    tree = Tree(fs=mock_session)
    indi = Indi(fid="INDI124", tree=tree)

    data = {
        "living": False,
        "names": [
            {
                "type": "http://gedcomx.org/BirthName",
                "preferred": False,  # All are alternate
                "nameForms": [
                    {"parts": [{"type": "http://gedcomx.org/Given", "value": "John"}]}
                ],
            }
        ],
    }

    indi.add_data(data)

    # Based on current logic "if not alt and not self.name", self.name will remain None if all are alt.
    # This is acceptable behavior for now, or we might want to relax it.
    # For now, just asserting it doesn't crash.
    assert indi.name is None
    assert len(indi.birthnames) == 1
