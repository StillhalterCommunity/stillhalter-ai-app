"""SQLite-Datenhaltung fuer den Familien-Finanztracker.

Alle Betraege in EUR. Vorzeichen-Konvention bei Transaktionen:
  + Einnahme, - Ausgabe. Umbuchungen zwischen eigenen Konten laufen
  ueber die Kategorie-Art 'transfer' und bleiben aus allen
  Einnahmen-/Ausgaben-Auswertungen draussen.
"""

import hashlib
import os
import sqlite3
from datetime import date

import pandas as pd

DB_PATH = os.environ.get(
    "FINANZEN_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "finanzen.db")
)

# Feste Budget-Gruppen (Reihenfolge = Anzeige-Reihenfolge)
GROUPS = [
    "Lebenshaltung",
    "Spaß & Freizeit",
    "Investment",
    "Anschaffungen",
    "Privat Sophia",
    "Privat Ich",
    "Philippa",
]

ACCOUNT_TYPES = {
    "giro": "Girokonto",
    "tagesgeld": "Tagesgeld / Sparkonto",
    "kreditkarte": "Kreditkarte",
    "depot": "Depot / Wertpapiere",
    "kinderdepot": "Kinderdepot (Philippa)",
    "bargeld": "Bargeld",
    "darlehen": "Darlehen / Kredit",
    "immodarlehen": "Immobiliendarlehen",
}

DEBT_TYPES = ("kreditkarte", "darlehen", "immodarlehen")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    owner_id INTEGER REFERENCES members(id),
    iban TEXT,
    start_balance REAL NOT NULL DEFAULT 0,
    interest_rate REAL,
    monthly_payment REAL,
    note TEXT,
    gocardless_id TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS categories(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    grp TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'ausgabe'  -- 'ausgabe' | 'einnahme' | 'transfer'
);
CREATE TABLE IF NOT EXISTS budgets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grp TEXT NOT NULL,
    month_from TEXT NOT NULL,             -- 'YYYY-MM', gilt ab diesem Monat
    amount REAL NOT NULL,
    UNIQUE(grp, month_from)
);
CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,                   -- 'YYYY-MM-DD'
    amount REAL NOT NULL,                 -- + Einnahme / - Ausgabe
    payee TEXT,
    description TEXT,
    category_id INTEGER REFERENCES categories(id),
    member_id INTEGER REFERENCES members(id),
    import_hash TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS bank_links(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requisition_id TEXT NOT NULL UNIQUE,
    institution TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
"""

_SEED_CATEGORIES = [
    # (Name, Gruppe, Art)
    ("Miete / Wohnen", "Lebenshaltung", "ausgabe"),
    ("Strom & Nebenkosten", "Lebenshaltung", "ausgabe"),
    ("Versicherungen", "Lebenshaltung", "ausgabe"),
    ("Lebensmittel & Drogerie", "Lebenshaltung", "ausgabe"),
    ("Mobilität", "Lebenshaltung", "ausgabe"),
    ("Gesundheit", "Lebenshaltung", "ausgabe"),
    ("Internet & Handy", "Lebenshaltung", "ausgabe"),
    ("Essen gehen", "Spaß & Freizeit", "ausgabe"),
    ("Reisen & Urlaub", "Spaß & Freizeit", "ausgabe"),
    ("Freizeit & Hobbys", "Spaß & Freizeit", "ausgabe"),
    ("Abos & Streaming", "Spaß & Freizeit", "ausgabe"),
    ("Aktien & ETFs", "Investment", "ausgabe"),
    ("Collectables", "Investment", "ausgabe"),
    ("Sonstige Investments", "Investment", "ausgabe"),
    ("Anschaffungen", "Anschaffungen", "ausgabe"),
    ("Privat Sophia", "Privat Sophia", "ausgabe"),
    ("Privat Ich", "Privat Ich", "ausgabe"),
    ("Sparplan Philippa", "Philippa", "ausgabe"),
    ("Ausgaben Philippa", "Philippa", "ausgabe"),
    ("Gehalt", "Einnahmen", "einnahme"),
    ("Mieteinnahmen", "Einnahmen", "einnahme"),
    ("Kindergeld", "Einnahmen", "einnahme"),
    ("Sonstige Einnahmen", "Einnahmen", "einnahme"),
    ("Umbuchung", "Sonstiges", "transfer"),
    ("Kredittilgung", "Sonstiges", "transfer"),
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")  # gleichzeitige Nutzung mehrerer Sessions
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO members(name) VALUES(?)", [("Ich",), ("Sophia",), ("Philippa",)]
            )
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO categories(name, grp, kind) VALUES(?,?,?)", _SEED_CATEGORIES
            )
        if conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] == 0:
            month = date.today().strftime("%Y-%m")
            conn.executemany(
                "INSERT INTO budgets(grp, month_from, amount) VALUES(?,?,0)",
                [(g, month) for g in GROUPS],
            )
        conn.commit()
    finally:
        conn.close()


def q(sql: str, params=()) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def exec_sql(sql: str, params=()) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def exec_many(sql: str, rows) -> int:
    """Fuehrt viele Inserts aus, ignoriert Duplikate (import_hash). Liefert Anzahl neuer Zeilen."""
    conn = get_conn()
    try:
        before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        conn.executemany(sql, rows)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        return after - before
    finally:
        conn.close()


def import_hash(account_id: int, tx_date: str, amount: float, payee: str, description: str) -> str:
    raw = f"{account_id}|{tx_date}|{amount:.2f}|{(payee or '').strip()}|{(description or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def members() -> pd.DataFrame:
    return q("SELECT * FROM members WHERE active=1 ORDER BY id")


def categories() -> pd.DataFrame:
    return q("SELECT * FROM categories ORDER BY grp, name")


def accounts(include_inactive: bool = False) -> pd.DataFrame:
    where = "" if include_inactive else "WHERE a.active=1"
    return q(
        f"""
        SELECT a.*, m.name AS owner,
               a.start_balance + COALESCE((
                   SELECT SUM(t.amount) FROM transactions t WHERE t.account_id = a.id
               ), 0) AS balance
        FROM accounts a LEFT JOIN members m ON m.id = a.owner_id
        {where}
        ORDER BY a.type, a.name
        """
    )


def effective_budgets(month: str) -> pd.DataFrame:
    """Budget je Gruppe, das fuer den Monat gilt (letzter Eintrag mit month_from <= month)."""
    return q(
        """
        SELECT b.grp, b.amount
        FROM budgets b
        WHERE b.month_from = (
            SELECT MAX(b2.month_from) FROM budgets b2
            WHERE b2.grp = b.grp AND b2.month_from <= ?
        )
        """,
        (month,),
    )


def month_flows(month: str) -> pd.DataFrame:
    """Alle Transaktionen eines Monats inkl. Kategorie/Gruppe/Art."""
    return q(
        """
        SELECT t.*, c.name AS category, c.grp, c.kind, a.name AS account, m.name AS member
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN members m ON m.id = t.member_id
        WHERE substr(t.date, 1, 7) = ?
        ORDER BY t.date DESC, t.id DESC
        """,
        (month,),
    )
