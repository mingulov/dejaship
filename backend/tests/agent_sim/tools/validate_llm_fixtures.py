from __future__ import annotations

import argparse

from tests.agent_sim._support.catalog import get_agent_sim_paths, load_app_catalog
from tests.agent_sim._support.fixture_store import read_fixture, validate_fixture_against_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate stored LLM fixtures for agent simulation.")
    return parser.parse_args()


def main() -> None:
    parse_args()
    root = get_agent_sim_paths().fixtures_root / "llm_outputs"
    if not root.exists():
        print(f"no fixture directory at {root}")
        return

    catalog = load_app_catalog()
    count = 0
    failures: list[str] = []
    for path in sorted(root.rglob("*.json")):
        fixture = read_fixture(path)
        drift_errors = validate_fixture_against_catalog(fixture, catalog=catalog)
        if drift_errors:
            failures.extend(f"{path}: {error}" for error in drift_errors)
            print(f"drift {path}")
        else:
            print(f"validated {path}")
        count += 1

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(f"{len(failures)} validation error(s) found")

    print(f"validated {count} fixture(s)")


if __name__ == "__main__":
    main()
