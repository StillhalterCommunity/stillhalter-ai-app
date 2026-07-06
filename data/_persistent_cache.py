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

# Cache-Verzeichnis:
#   - Lokal: data/_disk_cache (im Repo)
#   - Railway: STILLHALTER_DATA_DIR auf ein persistentes Volume zeigen lassen
#     (z.B. /data), sonst wird der Cache bei jedem Neustart/Deploy gelöscht.
_DATA_DIR = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
if _DATA_DIR:
    _CACHE_DIR = os.path.join(_DATA_DIR, "_disk_cache")
else:
    _CACHE_DIR = os.path.join(os.path.dirname(__file__), "_disk_cache")

try:
    os.makedirs(_CACHE_DIR, exist_ok=True)
except Exception:
    # Fallback auf lokales Verzeichnis wenn das Volume (noch) nicht gemountet ist
    _CACHE_DIR = os.path.join(os.path.dirname(__file__), "_disk_cache")
    os.makedirs(_CACHE_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


def _cache_path(key: str) -> str:
    safe = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(_CACHE_DIR, f"{safe}.pkl")


def scan_cache_path() -> str:
    """Pfad zur letzten Scan-Ergebnis-Datei (Top9 + Watchlist) — IM persistenten
    Volume, NICHT im Code-Ordner. Sonst überschreibt jeder Deploy den frischen
    Scan wieder mit einer evtl. mit-eingecheckten alten Datei.
    Liegt direkt im Datenverzeichnis (z.B. /data/last_scan_cache.pkl)."""
    return os.path.join(os.path.dirname(_CACHE_DIR), "last_scan_cache.pkl")


def save(key: str, data: Any, ttl_hours: float = 24.0) -> None:
    """Speichert Daten persistent auf Disk — ATOMAR (tmp + os.replace):
    Bei parallelen Nutzern/Threads kann sonst ein halb geschriebenes Pickle
    entstehen, das beim nächsten Laden als korrupt verworfen wird."""
    path = _cache_path(key)
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "wb") as f:
            pickle.dump({
                "key": key,
                "data": data,
                "saved_at": datetime.now().isoformat(),
                "ttl_hours": ttl_hours,
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception as e:
        logger.debug(f"Disk-Cache save failed for {key}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


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
