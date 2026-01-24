"""Tests based on live failures, fixes exceptions found in manual testing"""

import pytest

from getmyancestors.classes.tree.core import Fam, Tree


def test_add_marriage_none_sources(mock_session):
    """
    Test that add_marriage handles cases where the sources fetch returns None.
    This regression test ensures that a TypeError is not raised when sources is None.
    """
    tree = Tree(fs=mock_session)
    tree.sources = {}

    fam = Fam(tree=tree, num="F1")
    fam.fid = "FAM123"

    # Mock the sequence of calls:
    # 1. Fetch relationship details (returns valid data with source references)
    # 2. Fetch source descriptions (returns None, simulating the bug)
    mock_session.get_url.side_effect = [
        {
            "relationships": [
                {"facts": [], "sources": [{"descriptionId": "S1", "attribution": {}}]}
            ]
        },
        None,
    ]

    # This should not parse TypeError
    try:
        fam.add_marriage("FAM123")
    except TypeError:
        pytest.fail("add_marriage raised TypeError when sources was None")


def test_add_marriage_missing_source_key(mock_session):
    """
    Test that add_marriage verifies source existence in tree.sources before accessing it.
    This prevents KeyErrors when a referenced source was not successfully fetched.
    """
    tree = Tree(fs=mock_session)
    tree.sources = {}

    fam = Fam(tree=tree, num="F1")
    fam.fid = "FAM_KEYERROR"

    source_id = "MISSING_SOURCE_ID"

    # Mock the sequence:
    # 1. Fetch relationship details (referencing a source)
    # 2. Fetch source details (returns None, so the source is never added to tree.sources)
    mock_session.get_url.side_effect = [
        {
            "relationships": [
                {
                    "facts": [],
                    "sources": [
                        {
                            "descriptionId": source_id,
                            "attribution": {"changeMessage": "msg"},
                        }
                    ],
                }
            ]
        },
        None,
    ]

    # This should not raise KeyError
    try:
        fam.add_marriage("FAM_KEYERROR")
    except KeyError:
        pytest.fail(
            "add_marriage raised KeyError when source_fid was missing from tree.sources"
        )

    # Verify that the invalid source was truly skipped
    assert len(fam.sources) == 0
