"""Central config loader: config.yaml plus .env secrets."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_config(path: str | Path = ROOT / "config.yaml") -> dict[str, Any]:
    """Load YAML config and make all configured paths absolute."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["paths"] = {k: str(ROOT / v) for k, v in cfg["paths"].items()}
    return cfg


def get_secret(name: str, required: bool = True) -> str | None:
    """Read a secret from the environment; raise a clear error if missing."""
    val = os.getenv(name)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name} (see .env.example)")
    return val
