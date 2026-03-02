from __future__ import annotations

import re
from collections import defaultdict

from dejaship.config import settings
from tests.agent_sim._support.types import AppBrief, KeywordBuildResult


TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "annual",
    "base",
    "before",
    "being",
    "build",
    "built",
    "business",
    "businesses",
    "cannot",
    "clients",
    "companies",
    "company",
    "customer",
    "customers",
    "daily",
    "drive",
    "driven",
    "every",
    "firm",
    "firms",
    "focus",
    "founder",
    "founders",
    "growth",
    "handle",
    "helps",
    "higher",
    "lower",
    "local",
    "manager",
    "managers",
    "market",
    "meeting",
    "monthly",
    "multiple",
    "operators",
    "owner",
    "owners",
    "people",
    "per",
    "platform",
    "product",
    "projects",
    "recurring",
    "regional",
    "reporting",
    "revenue",
    "sequence",
    "service",
    "small",
    "software",
    "subscription",
    "subscriptions",
    "system",
    "teams",
    "their",
    "these",
    "they",
    "tool",
    "tools",
    "using",
    "weekly",
    "workflow",
    "workflows",
}
FIELD_WEIGHTS = {
    "category": 2,
    "target_customer": 4,
    "problem": 4,
    "workflow": 4,
    "recurring_revenue_model": 3,
    "pricing_shape": 2,
    "distribution_channel": 1,
    "constraints": 2,
    "must_have_features": 4,
    "success_metric": 2,
}
TARGET_FINAL_KEYWORD_COUNT = max(settings.MIN_KEYWORDS, min(10, settings.MAX_KEYWORDS))


def normalize_keyword_candidate(value: str) -> str | None:
    candidate = value.strip().lower().replace("_", "-")
    candidate = re.sub(r"\s+", "-", candidate)
    candidate = re.sub(r"[^a-z0-9\-]", "", candidate)
    candidate = re.sub(r"-{2,}", "-", candidate).strip("-")

    if (
        len(candidate) < settings.KEYWORD_MIN_LENGTH
        or len(candidate) > settings.KEYWORD_MAX_LENGTH
        or not candidate
    ):
        return None

    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]*[a-z0-9]", candidate):
        return None

    return candidate


def _extract_tokens(text: str) -> list[str]:
    tokens = [match.group(0) for match in TOKEN_PATTERN.finditer(text.lower())]
    return [
        token
        for token in tokens
        if len(token) >= settings.KEYWORD_MIN_LENGTH and token not in STOPWORDS
    ]


def _score_brief_terms(brief: AppBrief) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores: dict[str, int] = defaultdict(int)
    provenance: dict[str, set[str]] = defaultdict(set)

    def add_token(token: str, source: str, weight: int) -> None:
        normalized = normalize_keyword_candidate(token)
        if normalized is None:
            return
        scores[normalized] += weight
        provenance[normalized].add(source)

    add_token(brief.category, "field:category", FIELD_WEIGHTS["category"])

    fields = {
        "target_customer": brief.target_customer,
        "problem": brief.problem,
        "workflow": brief.workflow,
        "recurring_revenue_model": brief.recurring_revenue_model,
        "pricing_shape": brief.pricing_shape,
        "distribution_channel": brief.distribution_channel,
        "success_metric": brief.success_metric,
    }
    for field_name, text in fields.items():
        weight = FIELD_WEIGHTS[field_name]
        for token in _extract_tokens(text):
            add_token(token, f"field:{field_name}", weight)

    for field_name, values in {
        "constraints": brief.constraints,
        "must_have_features": brief.must_have_features,
    }.items():
        weight = FIELD_WEIGHTS[field_name]
        for item in values:
            for token in _extract_tokens(item):
                add_token(token, f"field:{field_name}", weight)

    return scores, {keyword: sorted(sources) for keyword, sources in provenance.items()}


def build_keyword_result(brief: AppBrief, llm_keywords: list[str]) -> KeywordBuildResult:
    scores, derived_provenance = _score_brief_terms(brief)
    provenance: dict[str, list[str]] = {}

    valid_llm_keywords: list[str] = []
    for value in llm_keywords:
        normalized = normalize_keyword_candidate(value)
        if normalized is None:
            continue
        if normalized not in valid_llm_keywords:
            valid_llm_keywords.append(normalized)
            provenance[normalized] = ["llm"]

    for keyword in brief.seed_keywords:
        provenance.setdefault(keyword, []).append("seed_keywords")

    derived_keywords = sorted(scores, key=lambda keyword: (-scores[keyword], keyword))
    for keyword in derived_keywords:
        provenance.setdefault(keyword, []).extend(
            source for source in derived_provenance.get(keyword, []) if source not in provenance[keyword]
        )

    final_keywords: list[str] = []
    for keyword in valid_llm_keywords + brief.seed_keywords + derived_keywords:
        if keyword in final_keywords:
            continue
        final_keywords.append(keyword)
        if len(final_keywords) >= TARGET_FINAL_KEYWORD_COUNT:
            break

    if len(final_keywords) < settings.MIN_KEYWORDS:
        raise ValueError(
            f"unable to build the minimum keyword count for brief '{brief.id}'"
        )

    return KeywordBuildResult(
        llm_keywords=valid_llm_keywords,
        derived_keywords=[keyword for keyword in derived_keywords if keyword not in brief.seed_keywords],
        final_keywords=final_keywords,
        keyword_provenance={keyword: sorted(set(provenance[keyword])) for keyword in final_keywords},
    )
