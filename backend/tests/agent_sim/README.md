# Agent Simulation Tests

This suite is the foundation for realistic MCP-driven multi-agent testing.

Goals:

- validate the catalog of app briefs used to drive agent behavior;
- validate model and scenario configuration before live generation exists;
- support deterministic replay tests that use stored LLM outputs later;
- exercise swarm simulations that hit the real `/mcp` endpoint.

Current baseline:

- the supported offline replay path is the pre-generated `smoke` fixture set
- non-live scenarios are expected to use stored smoke fixtures only
- broader model inventory remains available for optional live generation, but it is not required for the core suite
- the suite now also supports report-grade analysis runs with event logs, per-model metrics, and stale-cleanup simulation

Key files:

- `fixtures/app_catalog.yaml`: structured app briefs plus rendered narratives
- `fixtures/model_matrix.yaml`: model inventory and named model sets
- `fixtures/scenario_matrix.yaml`: scenario sizes, agent counts, and call targets
- `_support/types.py`: typed contracts for fixture files
- `_support/catalog.py`: fixture loaders
- `_support/config.py`: environment loading for live provider settings
- `_support/llm_provider.py`: OpenAI-compatible live provider wrapper using `instructor` + `pydantic`
- `_support/fixture_store.py`: versioned stored fixtures plus a synthetic fallback path
- `_support/agents.py`: persona-driven MCP workflows
- `_support/simulation.py`: plan building, call budgeting, and concurrent swarm execution
- `_support/reporting.py`: typed simulation report aggregation

Planned run modes:

```bash
cd backend
uv run pytest tests/agent_sim -m "agent_sim and not live_llm" -v
```

Live provider smoke and fixture generation should use the optional environment variables:

- `DEJASHIP_AGENT_SIM_LLM_PROVIDER`
- `DEJASHIP_AGENT_SIM_LLM_BASE_URL`
- `DEJASHIP_AGENT_SIM_LLM_API_KEY`
- `DEJASHIP_AGENT_SIM_DEFAULT_MODEL`
- `DEJASHIP_AGENT_SIM_MODEL_SET`

The environment only defines connectivity and defaults. The full model inventory lives in `fixtures/model_matrix.yaml`.

Provider stack for live fixture generation:

- `pydantic` models define the draft and stored artifact contracts
- `instructor` handles structured extraction and retries
- `openai.AsyncOpenAI` is used against OpenAI-compatible endpoints

Live generation behavior:

- `--skip-existing` resumes partial runs without rewriting successful fixtures
- `--model-alias` and `--brief-id` let you restart from a specific model or brief
- `--model-failure-threshold` marks problematic models as retry-later after repeated failed briefs so one slow or rate-limited model does not block the whole batch

Model inventory notes:

- the fixture catalog now includes a broader mix of model families, including Llama, Mixtral, DeepSeek, Kimi, MiniMax, Phi, Qwen, and Nemotron variants
- `smoke` is the current fully supported offline baseline
- wider coverage lives in `expanded` and `nightly` for optional live generation work
- models that are not yet verified on the target endpoint remain disabled in the matrix

Offline replay stack:

- stored fixtures are loaded through a `FixtureIndex`
- when a brief has no stored fixture yet, the suite synthesizes a deterministic baseline fixture from catalog data
- non-live swarm scenarios should not rely on that synthetic fallback; tests enforce stored-only usage for the smoke-backed scenarios
- concurrent swarm execution uses `anyio` task groups with one MCP session per virtual agent
- swarm assertions validate persisted DB state, terminal status transitions, and overlap pressure across claimed briefs
- agent summaries now include event timelines, unresolved claims, and per-model outcome aggregation
- stored fixture replay also checks prompt and brief hashes so catalog or prompt drift is detected early
- fixture directories are keyed by model alias only; provider details stay in fixture metadata

Report workflow:

- `run_agent_sim_report.py` runs a scenario on a fresh pgvector test container and exports JSON + Markdown artifacts
- reports include per-agent events, per-model summaries, quality metrics, and quality flags intended for human or LLM review
- `evaluate_cross_model_retrieval.py` measures whether a project claimed with one model is discoverable by other models under the current embedding text and similarity threshold
- `evaluate_similarity_thresholds.py` sweeps thresholds and recommends the best balance of exact retrieval, overlap retrieval, and false-positive control
- `evaluate_embedding_ablation.py` compares embedding-text variants and keyword-repeat sensitivity
- `run_quality_suite.py` emits a single analysis bundle with swarm, retrieval, threshold, ablation, and run metadata artifacts
- `compare_quality_bundles.py` diffs two saved quality bundles so search experiments can be judged without manual JSON review
- the durable quality framework, metric definitions, and improvement roadmap live in `docs/agent-sim-quality-framework.md`
- `stale-cleanup` simulates agents that never return and then validates cleanup behavior
- `hundred-agent` is an opt-in large scenario for manual stress analysis, not routine pytest

Current end-to-end coverage:

- `test_agent_swarm.py::test_agent_swarm_smoke_scenario` exercises a fast MCP swarm replay
- `test_agent_swarm.py::test_agent_swarm_local_scenario` is marked `slow` and drives the larger local scenario
- `test_agent_swarm.py::test_agent_swarm_extended_scenario` is marked `slow` and adds a higher-call deterministic replay tier
