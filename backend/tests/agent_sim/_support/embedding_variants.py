from __future__ import annotations

from dejaship.embeddings import build_embedding_text
from tests.agent_sim._support.types import AppBrief


def build_variant_text(
    *,
    variant: str,
    core_mechanic: str,
    keywords: list[str],
    brief: AppBrief,
    keyword_repeat: int,
) -> str:
    if variant == "current_combined":
        return _build_repeated_text(core_mechanic=core_mechanic, keywords=keywords, keyword_repeat=keyword_repeat)
    if variant == "core_only":
        return core_mechanic
    if variant == "keywords_only":
        return " ".join(keywords)
    if variant == "keywords_first_no_repeat":
        return " ".join([*keywords, core_mechanic])
    if variant == "core_plus_seed_keywords":
        return " ".join([core_mechanic, *brief.seed_keywords])
    raise ValueError(f"unknown embedding-text variant '{variant}'")


def _build_repeated_text(*, core_mechanic: str, keywords: list[str], keyword_repeat: int) -> str:
    if keyword_repeat <= 0:
        return " ".join([*keywords, core_mechanic])
    primary = keywords[:10]
    secondary = keywords[10:]
    parts: list[str] = []
    for _ in range(keyword_repeat):
        parts.extend(primary)
    parts.extend(secondary)
    parts.append(core_mechanic)
    return " ".join(parts)


def supported_embedding_variants() -> list[str]:
    return [
        "current_combined",
        "core_only",
        "keywords_only",
        "keywords_first_no_repeat",
        "core_plus_seed_keywords",
    ]
