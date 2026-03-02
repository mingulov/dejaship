from __future__ import annotations

import json


def render_intent_prompt(prompt_template: str, brief) -> str:
    brief_payload = {
        "id": brief.id,
        "title": brief.title,
        "category": brief.category,
        "target_customer": brief.target_customer,
        "problem": brief.problem,
        "workflow": brief.workflow,
        "recurring_revenue_model": brief.recurring_revenue_model,
        "pricing_shape": brief.pricing_shape,
        "distribution_channel": brief.distribution_channel,
        "constraints": brief.constraints,
        "must_have_features": brief.must_have_features,
        "seed_keywords": brief.seed_keywords,
        "anti_goals": brief.anti_goals,
        "success_metric": brief.success_metric,
        "prompt_rendered_brief": brief.prompt_rendered_brief,
    }
    return f"{prompt_template}\n\nBrief:\n{json.dumps(brief_payload, indent=2)}"
