"""Loads ``config.yaml``, the one place the Pollution Hunter constants live."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")


@cache
def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Parse the YAML file once. Callers must not modify the returned dict."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def wind_level() -> str:
    """The wind level the estimates use, ``100m`` or ``500m`` (``wind.level``)."""
    return load_config()["wind"]["level"]
