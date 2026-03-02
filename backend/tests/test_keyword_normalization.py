"""Tests for keyword normalization in IntentInput."""
import pytest
from dejaship.keyword_utils import normalize_keyword
from dejaship.schemas import IntentInput

VALID_KEYWORDS = ["invoicing", "automation", "freelance", "stripe", "payments"]


def test_normalize_keyword_lowercase():
    assert normalize_keyword("INVOICING") == "invoicing"


def test_normalize_keyword_spaces_to_hyphens():
    assert normalize_keyword("local business") == "local-business"


def test_normalize_keyword_strips_special_chars():
    assert normalize_keyword("seo!@#") == "seo"


def test_normalize_keyword_trims_hyphens():
    assert normalize_keyword("-seo-") == "seo"


def test_normalize_keyword_compound():
    assert normalize_keyword("  FIELD Service!  ") == "field-service"


def test_intent_input_normalizes_uppercase_keywords():
    inp = IntentInput(
        core_mechanic="test app",
        keywords=["INVOICING", "Automation", "freelance", "stripe", "payments"],
    )
    assert inp.keywords == ["invoicing", "automation", "freelance", "stripe", "payments"]


def test_intent_input_normalizes_spaces_in_keywords():
    inp = IntentInput(
        core_mechanic="test app",
        keywords=["local business", "seo tool", "web design", "marketing", "analytics"],
    )
    assert "local-business" in inp.keywords
    assert "seo-tool" in inp.keywords


def test_intent_input_rejects_too_short_after_normalization():
    with pytest.raises(Exception):
        IntentInput(
            core_mechanic="test app",
            keywords=["!!", "automation", "freelance", "stripe", "payments"],
        )


def test_intent_input_accepts_mixed_case():
    inp = IntentInput(
        core_mechanic="test app",
        keywords=["Invoice Tracking", "SaaS", "B2B Sales", "CRM", "pipeline"],
    )
    assert "invoice-tracking" in inp.keywords
    assert "saas" in inp.keywords
    assert "b2b-sales" in inp.keywords
