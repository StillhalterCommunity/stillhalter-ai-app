"""
Per-Nutzer-Speicher der Stillhalter AI (Volume: /data/users/<slug>.json).

Jeder eingeloggte Nutzer (auth_user) bekommt seinen eigenen Namespace —
Einstellungen, Flex-Query-Zugangsdaten, Depot-Snapshots usw. überleben
Deploys/Neustarts und sind strikt pro Nutzer getrennt. Schreibzugriffe
sind atomar (tmp + os.replace) — sicher bei parallelen Sessions.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any


def _users_dir() -> str:
    base = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
    if not base:
        base = os.path.join(os.path.dirname(__file__))
    d = os.path.join(base, "users")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _slug(username: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (username or "anonym").lower()).strip("_")
    return s or "anonym"


def _path(username: str) -> str:
    return os.path.join(_users_dir(), f"{_slug(username)}.json")


def load_user(username: str) -> dict:
    p = _path(username)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_user(username: str, data: dict) -> None:
    p = _path(username)
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, p)


def get_value(username: str, key: str, default: Any = None) -> Any:
    return load_user(username).get(key, default)


def set_value(username: str, key: str, value: Any) -> None:
    d = load_user(username)
    d[key] = value
    d["_updated"] = datetime.now().isoformat(timespec="seconds")
    save_user(username, d)


def append_snapshot(username: str, key: str, snapshot: dict, keep: int = 400) -> None:
    """Hängt einen Zeitreihen-Snapshot an (z. B. NLV-Verlauf), begrenzt Länge."""
    d = load_user(username)
    arr = d.get(key) or []
    arr.append(snapshot)
    d[key] = arr[-keep:]
    d["_updated"] = datetime.now().isoformat(timespec="seconds")
    save_user(username, d)
