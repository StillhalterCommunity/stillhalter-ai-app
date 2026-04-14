"""
Stillhalter AI App — Authentifizierung & Login-Tracking
Nutzerspezifische Passwörter + CSV-Protokollierung.
"""

from __future__ import annotations
import csv
import os
from datetime import datetime

# ── Nutzerliste ───────────────────────────────────────────────────────────────
# Format: "Passwort": "Anzeigename"
# Passwort-Schema: {Vorname}-Sth-{Nummer}  (leicht merkbar, Name eindeutig erkennbar)
# Hier neue Nutzer eintragen ↓

USERS: dict[str, str] = {
    # ── Admin ──────────────────────────────────────────────────────────────────
    "Oliver-Sth-00":    "Oliver Riebartsch",
    "1111":             "Oliver Riebartsch",   # Schnell-Login (nur lokal testen)

    # ── Beta-Tester ───────────────────────────────────────────────────────────
    "Stefan-Sth-01":    "Stefan Zenkel",
    "Jan-Sth-02":       "Jan Bechler",
    "Leon-Sth-03":      "Leon Benedens",
    "Tobias-Sth-04":    "Tobias Mayer",
}

# ── Log-Datei ────────────────────────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.dirname(__file__), "login_log.csv")
_LOG_HEADER = ["Zeitstempel", "Nutzer", "Aktion", "Session-ID"]


def _ensure_log():
    """Erstellt Login-Log-Datei falls nicht vorhanden."""
    if not os.path.exists(_LOG_PATH):
        with open(_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_LOG_HEADER)


def check_password(password: str) -> str | None:
    """
    Prüft das Passwort gegen die Nutzerliste.
    Gibt den Anzeigenamen zurück, oder None wenn ungültig.
    """
    return USERS.get(password.strip())


def log_event(username: str, action: str, session_id: str = "") -> None:
    """
    Protokolliert ein Login-Ereignis in der CSV-Datei.
    Aktionen: 'login', 'logout', 'page_visit', 'session_end'
    """
    try:
        _ensure_log()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([ts, username, action, session_id])
    except Exception:
        pass  # Logging-Fehler niemals die App crashen lassen


def load_log() -> list[dict]:
    """Lädt alle Login-Events als Liste von Dicts (für Admin-Ansicht)."""
    try:
        _ensure_log()
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []
