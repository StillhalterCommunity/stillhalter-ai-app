"""
Wartungsmodus-Steuerung für die Stillhalter AI App.
Flag wird in einer Datei gespeichert — kein Code-Deploy nötig zum Aktivieren.
"""

import os

_FLAG_PATH = os.path.join(os.path.dirname(__file__), "maintenance.flag")

ADMIN_USERS = {"Oliver Riebartsch"}


def is_maintenance() -> bool:
    """Gibt True zurück wenn Wartungsmodus aktiv ist."""
    return os.path.exists(_FLAG_PATH)


def enable() -> None:
    """Schaltet Wartungsmodus ein."""
    with open(_FLAG_PATH, "w") as f:
        f.write("maintenance")


def disable() -> None:
    """Schaltet Wartungsmodus aus."""
    try:
        os.remove(_FLAG_PATH)
    except FileNotFoundError:
        pass


def is_admin(username: str) -> bool:
    """Gibt True zurück wenn der Nutzer Admin-Rechte hat."""
    return username in ADMIN_USERS
