# Agent Simulation Test Suite Plan

## Goal

Build a thorough test suite that exercises DejaShip through its real MCP interface under realistic multi-agent behavior.

The suite should answer four questions:

1. Can many agents use the MCP protocol repeatedly without protocol or state-machine failures?
2. Does the semantic neighborhood logic create useful separation between unrelated ideas and useful collision pressure between related ideas?
3. Can we replay realistic LLM-produced intents deterministically without paying provider costs during normal tests?
4. Can we optionally run a live-provider smoke flow against a real OpenAI-compatible endpoint to validate prompt contracts?

## Scope Boundaries

- Default test runs must be deterministic and offline after fixtures are generated.
- Live LLM calls are allowed only in explicit fixture generation commands and explicit smoke tests.
- The primary contract under test is the backend MCP Streamable HTTP endpoint, not only the REST routes and not primarily the Node wrapper.
- The suite belongs in `backend/tests/agent_sim/` so it can reuse the existing pytest, pgvector, FastAPI, and testcontainers harness.

## Refined Architecture

The suite should follow a strict artifact pipeline:

1. Static catalog brief
2. Prompt template plus rendered prompt
3. Live provider draft output
4. Deterministic keyword synthesis
5. Stored fixture JSON
6. Deterministic replay and swarm simulation

This split matters because only steps 3 and 4 should ever change the semantic payload, while steps 5 and 6 must stay reproducible.

Additional design rules:

- replay tests must never mutate stored fixtures;
- overlap metadata is for scenario design and assertions, not for keyword generation;
- fixture files must carry enough hashes and metadata to detect prompt drift;
- live provider code should only return typed drafts, never write files directly.
- the offline swarm suite must have a deterministic synthetic baseline when no stored fixtures exist yet.

## Architecture Improvements

Two additional patterns make the suite more practical and less brittle:

1. `FixtureIndex`
   It should index stored fixtures by `brief_id` and `model_alias`, and offer a single lookup API for replay code.

2. Synthetic baseline fixtures
   Local runs should not block on live fixture generation. If a stored fixture is missing, the suite should synthesize a baseline fixture from the catalog brief, deterministic keyword builder, and a typed synthetic metadata record.

3. Concurrent swarm orchestration
   Agent execution should use `anyio` task groups with one MCP session per virtual agent. Tests should assert against typed reports, not raw logs.

4. Persistence-aware assertions
   Swarm tests should compare their typed report against a DB snapshot so the suite validates the real claim/update state machine, not only client-side counters.

5. Drift detection
   Stored fixture replay should verify both `brief_hash` and `prompt_hash` against the current catalog and prompt templates so stale fixtures fail explicitly after catalog or prompt edits.

## Proposed Layout

```text
backend/tests/agent_sim/
  README.md
  conftest.py
  fixtures/
    app_catalog.yaml
    model_matrix.yaml
    scenario_matrix.yaml
    llm_outputs/
      v1/
        <provider>/
          <model>/
            <brief_id>.json
  prompts/
    intent_from_brief_v1.md
    decision_after_check_v1.md
  _support/
    types.py
    catalog.py
    keyword_builder.py
    mcp_client.py
    llm_provider.py
    fixture_store.py
    agents.py
    simulation.py
    assertions.py
    reporting.py
  tools/
    generate_llm_fixtures.py
    validate_llm_fixtures.py
  test_catalog_contracts.py
  test_fixture_replay.py
  test_agent_swarm.py
  test_live_llm_smoke.py
  test_mcp_stdio_wrapper_smoke.py
```

## Dataset Design

### App Catalog

The catalog should contain 20 app briefs.

The briefs should not all be unrelated. The suite needs both separation and collision.

Recommended split:

- 8 isolated ideas with low expected overlap.
- 8 ideas in 4 near-neighbor pairs.
- 4 ambiguous ideas that sit between categories and may collide with multiple neighbors.

Each brief should be stored as structured data plus a rendered narrative.

Required fields:

- `id`
- `title`
- `target_customer`
- `problem`
- `workflow`
- `recurring_revenue_model`
- `pricing_shape`
- `constraints`
- `must_have_features`
- `expected_overlap_group`
- `prompt_rendered_brief`

Recommended additional fields:

- `seed_keywords`
- `category`
- `distribution_channel`
- `compliance_notes`
- `anti_goals`
- `success_metric`

### Why Structured Fields Matter

The structured fields are not just for documentation. They will feed both prompt rendering and keyword generation.

This is preferable to storing only long prose because:

- it is easier to validate and diff;
- it keeps fixture generation reproducible;
- it gives a deterministic fallback if an LLM output is weak;
- it allows later tuning of keyword extraction without rewriting all briefs.

## Keyword Generation Decision

Yes, the generator should derive keywords from the structured brief fields to improve quality.

The suite should use a two-stage keyword strategy:

1. LLM proposes an intent payload from the rendered brief.
2. A deterministic keyword builder merges and validates signal from structured fields.

### Keyword Sources

Input sources:

- `target_customer`
- `problem`
- `workflow`
- `recurring_revenue_model`
- `pricing_shape`
- `constraints`
- `must_have_features`
- optional `seed_keywords`

### Keyword Builder Rules

The keyword builder should:

- normalize to lowercase;
- tokenize candidate phrases into hyphenated keywords;
- keep only values accepted by the current `IntentInput` schema;
- deduplicate;
- rank terms by relevance;
- guarantee at least `MIN_KEYWORDS`;
- keep a provenance map for each final keyword.

Suggested precedence:

1. LLM keywords that pass schema validation.
2. Explicit `seed_keywords` from the catalog.
3. Deterministic keywords derived from `target_customer`, `problem`, `workflow`, and `must_have_features`.
4. Deterministic keywords derived from pricing and revenue model.

The final fixture should store:

- `llm_keywords`
- `derived_keywords`
- `final_keywords`
- `keyword_provenance`

This keeps tests realistic while preserving auditability.

## Prompt and Fixture Generation

### Live Provider Source

The fixture generator should support OpenAI-compatible endpoints and load configuration from the repo `.env` or the process environment.

Expected settings:

- `DEJASHIP_AGENT_SIM_LLM_PROVIDER`
- `DEJASHIP_AGENT_SIM_LLM_BASE_URL`
- `DEJASHIP_AGENT_SIM_LLM_API_KEY`
- `DEJASHIP_AGENT_SIM_DEFAULT_MODEL`
- `DEJASHIP_AGENT_SIM_MODEL_SET`

The environment should define connection details and defaults, not the full model catalog.

Reason:

- the endpoint, auth, and default selection belong in environment-specific config;
- the full model inventory can grow to dozens of entries and needs metadata, weights, and comments;
- the suite should switch between model sets without editing secrets.

If the live provider is NVIDIA NIM, the generator should still treat it generically and not hardcode provider-specific behavior beyond the OpenAI-compatible API surface.

### Generator Behavior

`tools/generate_llm_fixtures.py` should:

1. Load the catalog.
2. Load one or more model identifiers from `model_matrix.yaml`, using `DEJASHIP_AGENT_SIM_MODEL_SET` as the default named set.
3. Render the intent-generation prompt for each brief.
4. Request structured output from the live provider.
5. Validate output against the current `IntentInput` constraints.
6. Run the deterministic keyword builder.
7. Persist a normalized fixture JSON file.

Each fixture JSON should contain:

- `brief_id`
- `provider`
- `model`
- `prompt_version`
- `brief_hash`
- `raw_prompt`
- `raw_response`
- `normalized_output`
- `llm_core_mechanic`
- `llm_keywords`
- `derived_keywords`
- `final_intent_input`
- `planned_resolution`

The generator should be architected as separate layers:

- provider client
- prompt renderer
- keyword builder
- fixture store

This keeps live provider behavior isolated from replay and allows unit tests to cover almost all logic without network access.

Recommended implementation:

- `pydantic` models for all draft and stored fixture artifacts
- `instructor` for typed structured extraction with retries
- `openai.AsyncOpenAI` as the base client for OpenAI-compatible endpoints

### Model Matrix

`model_matrix.yaml` should hold the model inventory and named groups.

It should define:

- `sets`
- `models`

Each model entry should support fields like:

- `model`
- `role`
- `weight`
- `enabled`
- `notes`

Recommended named sets:

- `primary`
- `cheap`
- `reasoning`
- `smoke`
- `default`
- `nightly`

Example shape:

```yaml
sets:
  smoke:
    - nim-fast
    - nim-balanced
  default:
    - nim-fast
    - nim-balanced
    - nim-reasoning
  nightly:
    - nim-fast
    - nim-balanced
    - nim-reasoning
    - nim-large
    - nim-alt-1

models:
  nim-fast:
    model: meta/llama-3.1-8b-instruct
    role: cheap
    weight: 3
    enabled: true
  nim-balanced:
    model: mistralai/mixtral-8x7b-instruct-v0.1
    role: default
    weight: 4
    enabled: true
  nim-reasoning:
    model: deepseek-ai/deepseek-r1-distill-llama-70b
    role: reasoning
    weight: 2
    enabled: true
```

This allows the repository to support 30 or more models without bloating `.env`.

### Scenario Matrix

`scenario_matrix.yaml` should define execution scale independently from the model inventory.

Each scenario should support fields like:

- `agent_count`
- `total_calls_target`
- `model_set`
- `persona_mix`
- `brief_selection_strategy`

Example shape:

```yaml
scenarios:
  local:
    agent_count: 10
    total_calls_target: 300
    model_set: default
  stress:
    agent_count: 20
    total_calls_target: 1000
    model_set: nightly
```

This keeps agent count decoupled from model count.

## Simulation Design

### Phase 1 Scale

Initial deterministic swarm:

- 10 virtual agents
- 300 to 500 MCP tool calls total
- model set selected from `scenario_matrix.yaml`

### Phase 2 Scale

Expansion target:

- 20 virtual agents
- around 1000 MCP tool calls total
- broader model set, potentially covering dozens of stored model outputs over repeated runs

The first implementation should keep the architecture ready for phase 2, but the default suite should remain phase 1 until runtime and flakiness are proven acceptable.

### Agent Model

Each virtual agent should have:

- `agent_id`
- `persona`
- `model_name`
- `assigned_briefs`
- `seed`
- `policy`

Agent count should not equal model count.

The simulation should assign agents to models by weighted sampling from the selected `model_set`, so a run can use 10 or 20 agents while still drawing behavior from a larger catalog of 30 available models over time.

Recommended personas:

- cautious
- aggressive
- overlap-averse
- overlap-tolerant
- reviser
- shipper
- abandoner
- monitor-first
- noisy-prompter
- duplicate-prone

### Agent Flow

Each agent should operate through the real MCP endpoint:

1. initialize MCP session;
2. list tools;
3. choose a brief;
4. generate or load intent fixture;
5. call `dejaship_check_airspace`;
6. decide whether to revise, claim, or skip;
7. possibly re-check after others have claimed;
8. claim if policy allows;
9. update to `shipped` or `abandoned` later.

Agents should not all perform the same sequence. The scenario matrix should introduce different timing, retries, and revision probabilities.

## Test Files

### `test_catalog_contracts.py`

Purpose:

- validate the 20-brief catalog;
- validate overlap-group design;
- validate rendered brief presence and length;
- validate seed keyword quality.

### `test_fixture_replay.py`

Purpose:

- validate stored fixtures against current prompt version;
- validate `final_intent_input` against schema;
- validate keyword provenance coverage;
- ensure deterministic replay remains stable.

### `test_agent_swarm.py`

Purpose:

- run the main multi-agent simulation against a fresh DB;
- assert system invariants after hundreds of MCP calls.

Assertions:

- claim IDs are unique;
- invalid updates fail;
- abandoned claims are excluded from active closest results;
- shipped claims can still appear in density and closest lists;
- related briefs create collision pressure;
- unrelated briefs remain mostly separate;
- final DB counts match the simulation report.

### `test_live_llm_smoke.py`

Purpose:

- optional smoke test for the live provider and prompt contract;
- not part of the default suite.

Run only when the environment is explicitly configured.

### `test_mcp_stdio_wrapper_smoke.py`

Purpose:

- lightweight verification that `mcp-client/` still works as a stdio wrapper;
- lower priority than backend MCP tests.

## Pytest Markers

Add markers such as:

- `agent_sim`
- `live_llm`
- `slow`

Recommended usage:

```bash
cd backend
uv run pytest tests/agent_sim -m "agent_sim and not live_llm" -v
```

Live smoke:

```bash
cd backend
uv run pytest tests/agent_sim/test_live_llm_smoke.py -m live_llm -v
```

## MCP Client Strategy

Use the Python `mcp.client.streamable_http` client for the main suite.

Reason:

- it hits the real Streamable HTTP MCP interface;
- it keeps the suite inside the backend pytest environment;
- it avoids making the Node wrapper a hard dependency of the core simulation tests.

The stdio wrapper should get only a small smoke test.

## Reporting

Each simulation run should produce a structured report object with:

- total MCP calls;
- checks, claims, updates;
- skipped ideas;
- revised intents;
- collisions detected;
- final status counts;
- per-agent summary;
- per-overlap-group summary.

The report should be asserted in tests and optionally written to a temp file for debugging.

## Security and Secret Handling

- The generator must never print the API key.
- Raw provider payloads may contain sensitive metadata and should be stored only in local fixtures intended for replay.
- CI should not run live-provider tests unless explicitly enabled.

## Implementation Sequence

1. Create `backend/tests/agent_sim/` scaffolding, README, pytest markers, and shared support types.
2. Add the 20-brief catalog and overlap-group design.
3. Implement the keyword builder and catalog validators.
4. Implement the OpenAI-compatible live fixture generator using `DEJASHIP_AGENT_SIM_LLM_*`, `DEJASHIP_AGENT_SIM_DEFAULT_MODEL`, and `DEJASHIP_AGENT_SIM_MODEL_SET`.
5. Implement fixture validation and deterministic replay tests.
6. Implement the 10-agent swarm runner over the Python MCP Streamable HTTP client.
7. Add the optional live-provider smoke test.
8. Add the small stdio wrapper smoke test for `mcp-client/`.
9. Expand to 20 agents and about 1000 calls only after phase 1 proves stable and runtime remains acceptable.

## Non-Goals

- Do not make default pytest runs depend on external LLM availability.
- Do not require exact string matches from live model outputs.
- Do not use only unrelated briefs, because that under-tests DejaShip's core value.
- Do not couple the main simulation to the Node wrapper.
