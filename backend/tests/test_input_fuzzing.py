"""Property-based tests for input validation boundaries."""
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from dejaship.schemas import IntentInput


# Valid keyword: 3-40 chars, lowercase alphanumeric + hyphens, no leading/trailing hyphen
valid_keyword = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-",
    min_size=3,
    max_size=40,
).filter(lambda s: s[0] != "-" and s[-1] != "-")

valid_keywords_list = st.lists(valid_keyword, min_size=5, max_size=15, unique=True)
valid_mechanic = st.text(
    min_size=1,
    max_size=250,
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
)


@given(mechanic=valid_mechanic, keywords=valid_keywords_list)
@settings(max_examples=200)
def test_valid_inputs_always_parse(mechanic: str, keywords: list[str]):
    """Any input matching the constraints should parse without error."""
    result = IntentInput(core_mechanic=mechanic, keywords=keywords)
    assert len(result.keywords) >= 5


@given(
    short_kw=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=2),
)
@settings(max_examples=50)
def test_short_keywords_rejected(short_kw: str):
    """Keywords shorter than 3 chars must be rejected."""
    assume(len(short_kw) < 3)
    with pytest.raises(ValidationError):
        IntentInput(
            core_mechanic="test mechanic",
            keywords=[short_kw, "valid1", "valid2", "valid3", "valid4"],
        )


@given(
    bad_kw=st.text(alphabet=string.ascii_uppercase, min_size=3, max_size=10),
)
@settings(max_examples=50)
def test_uppercase_keywords_normalized(bad_kw: str):
    """Keywords with uppercase characters are auto-normalized to lowercase."""
    result = IntentInput(
        core_mechanic="test mechanic",
        keywords=[bad_kw, "valid1", "valid2", "valid3", "valid4"],
    )
    for kw in result.keywords:
        assert kw == kw.lower()


@given(
    keywords=st.lists(valid_keyword, min_size=0, max_size=4, unique=True),
)
@settings(max_examples=50)
def test_too_few_keywords_rejected(keywords: list[str]):
    """Fewer than 5 keywords must be rejected."""
    assume(len(keywords) < 5)
    with pytest.raises(ValidationError):
        IntentInput(core_mechanic="test mechanic", keywords=keywords)


def test_empty_mechanic_rejected():
    """Empty core_mechanic must be rejected."""
    with pytest.raises(ValidationError):
        IntentInput(core_mechanic="", keywords=["alpha", "bravo", "charlie", "delta", "echo"])
