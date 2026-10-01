"""Tiny JSON file cache so API calls are never repeated."""
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


class JsonCache:
    def __init__(self, cache_dir: str) -> None:
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def set(self, key: str, value: Any) -> None:
        self._path(key).write_text(json.dumps(value), encoding="utf-8")

    def get_or_fetch(self, key: str, fetch: Callable[[], Any]) -> Any:
        """Return cached value, else call fetch(), cache and return it."""
        hit = self.get(key)
        if hit is not None:
            return hit
        value = fetch()
        self.set(key, value)
        return value
