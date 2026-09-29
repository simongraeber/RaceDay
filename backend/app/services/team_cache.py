import time
from typing import Any

TTL_S = 120

_entries: dict[Any, tuple[float, Any]] = {}


def get(key: Any) -> Any | None:
    hit = _entries.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def put(key: Any, value: Any) -> None:
    _entries[key] = (time.monotonic() + TTL_S, value)


def clear() -> None:
    _entries.clear()
    from app.services import map_data

    map_data.clear()
