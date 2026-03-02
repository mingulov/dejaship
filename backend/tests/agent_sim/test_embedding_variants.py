import pytest

from tests.agent_sim._support.embedding_variants import (
    build_variant_text,
    supported_embedding_variants,
)


pytestmark = pytest.mark.agent_sim


def test_supported_embedding_variants_are_stable():
    assert "current_combined" in supported_embedding_variants()
    assert "core_only" in supported_embedding_variants()


def test_build_variant_text_supports_core_only(agent_sim_catalog):
    brief = agent_sim_catalog.briefs[0]
    text = build_variant_text(
        variant="core_only",
        core_mechanic="Core mechanic",
        keywords=["one", "two"],
        brief=brief,
        keyword_repeat=2,
    )

    assert text == "Core mechanic"
