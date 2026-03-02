from __future__ import annotations

from pathlib import Path

import yaml

from tests.agent_sim._support.types import (
    AgentSimPaths,
    AppCatalog,
    ModelMatrix,
    ModelEntry,
    ScenarioMatrix,
)


def get_agent_sim_paths() -> AgentSimPaths:
    support_file = Path(__file__).resolve()
    agent_sim_root = support_file.parents[1]
    backend_root = support_file.parents[3]
    repo_root = support_file.parents[4]
    return AgentSimPaths(
        repo_root=repo_root,
        backend_root=backend_root,
        agent_sim_root=agent_sim_root,
        fixtures_root=agent_sim_root / "fixtures",
        prompts_root=agent_sim_root / "prompts",
    )


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def load_prompt_text(prompt_name: str) -> str:
    paths = get_agent_sim_paths()
    prompt_path = paths.prompts_root / f"{prompt_name}.md"
    return prompt_path.read_text()


def load_app_catalog() -> AppCatalog:
    paths = get_agent_sim_paths()
    return AppCatalog.model_validate(_load_yaml(paths.fixtures_root / "app_catalog.yaml"))


def load_model_matrix() -> ModelMatrix:
    paths = get_agent_sim_paths()
    return ModelMatrix.model_validate(_load_yaml(paths.fixtures_root / "model_matrix.yaml"))


def load_scenario_matrix(model_matrix: ModelMatrix | None = None) -> ScenarioMatrix:
    paths = get_agent_sim_paths()
    scenario_matrix = ScenarioMatrix.model_validate(
        _load_yaml(paths.fixtures_root / "scenario_matrix.yaml")
    )
    if model_matrix is not None:
        known_sets = set(model_matrix.sets)
        missing = {
            f"{scenario_name}:{scenario.model_set}"
            for scenario_name, scenario in scenario_matrix.scenarios.items()
            if scenario.model_set not in known_sets
        }
        if missing:
            raise ValueError(f"scenarios reference unknown model sets: {sorted(missing)}")
    return scenario_matrix


def resolve_model_set(model_matrix: ModelMatrix, set_name: str) -> list[tuple[str, ModelEntry]]:
    model_ids = model_matrix.sets.get(set_name)
    if model_ids is None:
        raise ValueError(f"unknown model set '{set_name}'")

    resolved = [(model_id, model_matrix.models[model_id]) for model_id in model_ids]
    enabled = [(model_id, model) for model_id, model in resolved if model.enabled]
    if not enabled:
        raise ValueError(f"model set '{set_name}' has no enabled models")
    return enabled
