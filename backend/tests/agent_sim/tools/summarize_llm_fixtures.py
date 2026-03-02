from __future__ import annotations

from collections import Counter

from tests.agent_sim._support.catalog import load_app_catalog, load_model_matrix
from tests.agent_sim._support.fixture_store import iter_fixture_paths, read_fixture


def main() -> None:
    catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    fixture_paths = iter_fixture_paths()

    fixture_count_by_model: Counter[str] = Counter()
    brief_count_by_model: dict[str, set[str]] = {}

    for path in fixture_paths:
        fixture = read_fixture(path)
        model_alias = fixture.metadata.model_alias
        fixture_count_by_model[model_alias] += 1
        brief_count_by_model.setdefault(model_alias, set()).add(fixture.brief_id)

    enabled_models = [alias for alias, entry in model_matrix.models.items() if entry.enabled]
    total_briefs = len(catalog.briefs)

    print(f"stored fixtures: {len(fixture_paths)}")
    print(f"catalog briefs: {total_briefs}")
    print(f"enabled models: {len(enabled_models)}")
    print("coverage by enabled model:")
    for model_alias in sorted(enabled_models):
        brief_count = len(brief_count_by_model.get(model_alias, set()))
        fixture_count = fixture_count_by_model.get(model_alias, 0)
        print(f"  {model_alias}: {brief_count}/{total_briefs} briefs, {fixture_count} fixture(s)")


if __name__ == "__main__":
    main()
