"""
Persistenter Disk-Cache für Marktdaten.
Funktioniert als Fallback wenn @st.cache_data leer zurückgibt
(z.B. nach API-Fehler, Rate-Limit oder App-Neustart).

Strategie:
- Erfolgreiche Fetches → auf Disk speichern
- Leere/fehlgeschlagene Fetches → Disk-Backup laden wenn vorhanden
- Disk-TTL deutlich länger als In-Memory-TTL (z.B. 24h statt 1h)
"""

import os
import pickle
import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "_disk_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


def _cache_path(key: str) -> str:
    safe = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(_CACHE_DIR, f"{safe}.pkl")


def save(key: str, data: Any, ttl_hours: float = 24.0) -> None:
    """Speichert Daten persistent auf Disk."""
    try:
        with open(_cache_path(key), "wb") as f:
            pickle.dump({
                "key": key,
                "data": data,
                "saved_at": datetime.now().isoformat(),
                "ttl_hours": ttl_hours,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.debug(f"Disk-Cache save failed for {key}: {e}")


def load(key: str, max_age_hours: float = 24.0) -> Optional[Any]:
    """Lädt Daten vom Disk-Cache. None wenn nicht vorhanden oder zu alt."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
        age_h = (datetime.now() - datetime.fromisoformat(obj["saved_at"])).total_seconds() / 3600
        if age_h > max_age_hours:
            return None
        return obj["data"]
    except Exception:
        return None


def load_latest(key: str) -> Optional[Any]:
    """Lädt vom Disk-Cache egal wie alt — Notfall-Fallback."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
        return obj.get("data")
    except Exception:
        return None


def age_hours(key: str) -> Optional[float]:
    """Gibt Alter des Cache-Eintrags in Stunden zurück, None wenn nicht vorhanden."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
        return (datetime.now() - datetime.fromisoformat(obj["saved_at"])).total_seconds() / 3600
    except Exception:
        return None


def clear_all() -> int:
    """Löscht alle Disk-Cache-Dateien. Gibt Anzahl gelöschter Dateien zurück."""
    count = 0
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith(".pkl"):
            try:
                os.remove(os.path.join(_CACHE_DIR, fname))
                count += 1
            except Exception:
                pass
    return count
