# Agent Simulation Tests

This suite is the foundation for realistic MCP-driven multi-agent testing.

Goals:

- validate the catalog of app briefs used to drive agent behavior;
- validate model and scenario configuration before live generation exists;
- support deterministic replay tests that use stored LLM outputs later;
- exercise swarm simulations that hit the real `/mcp` endpoint.

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
- `openai.AsyncOpenAI` is used against OpenAI-compatible endpoints such as NVIDIA NIM

Offline replay stack:

- stored fixtures are loaded through a `FixtureIndex`
- when a brief has no stored fixture yet, the suite synthesizes a deterministic baseline fixture from catalog data
- concurrent swarm execution uses `anyio` task groups with one MCP session per virtual agent
- swarm assertions validate persisted DB state, terminal status transitions, and overlap pressure across claimed briefs
- stored fixture replay also checks prompt and brief hashes so catalog or prompt drift is detected early

Current end-to-end coverage:

- `test_agent_swarm.py::test_agent_swarm_smoke_scenario` exercises a fast MCP swarm replay
- `test_agent_swarm.py::test_agent_swarm_local_scenario` is marked `slow` and drives the larger local scenario
- `test_agent_swarm.py::test_agent_swarm_extended_scenario` is marked `slow` and adds a higher-call deterministic replay tier
