"""Loads config/assumptions.yaml. All tunable numbers live in that file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSUMPTIONS_PATH = ROOT / "config" / "assumptions.yaml"


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict:
    with open(path or ASSUMPTIONS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_text() -> str:
    return ASSUMPTIONS_PATH.read_text(encoding="utf-8")
