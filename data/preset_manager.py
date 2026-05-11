"""
Stillhalter AI App — Benutzerdefinierte Filter-Presets
Speichert und lädt benannte Scanner-Konfigurationen (JSON-persistiert).
"""

import json
import os
from typing import Optional

_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "user_presets.json")


def load_presets() -> dict:
    """Lädt alle gespeicherten Presets. Gibt leeres Dict zurück wenn keine vorhanden."""
    if not os.path.exists(_PRESETS_PATH):
        return {}
    try:
        with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_preset(name: str, config: dict) -> bool:
    """Speichert einen Preset unter dem gegebenen Namen. Gibt True bei Erfolg zurück."""
    if not name or not name.strip():
        return False
    presets = load_presets()
    presets[name.strip()] = config
    try:
        with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def delete_preset(name: str) -> bool:
    """Löscht einen Preset. Gibt True zurück wenn erfolgreich."""
    presets = load_presets()
    if name not in presets:
        return False
    del presets[name]
    try:
        with open(_PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_preset(name: str) -> Optional[dict]:
    """Gibt einen einzelnen Preset zurück oder None."""
    return load_presets().get(name)
