"""Generischer CSV-Import fuer Bank-Exporte (deutsche Formate)."""

import io

import pandas as pd


def read_bank_csv(raw: bytes) -> pd.DataFrame:
    """Liest Bank-CSVs robust: probiert Trennzeichen ;/, und Encodings utf-8/latin-1."""
    last_err = None
    for enc in ("utf-8-sig", "latin-1"):
        for sep in (";", ",", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(raw), sep=sep, encoding=enc, dtype=str,
                                 skip_blank_lines=True)
                if df.shape[1] >= 2:
                    df.columns = [str(c).strip() for c in df.columns]
                    return df
            except Exception as e:  # naechste Kombination probieren
                last_err = e
    raise ValueError(f"CSV konnte nicht gelesen werden: {last_err}")


def parse_amount(value: str) -> float:
    """'1.234,56' / '-12,30 €' / '1,234.56' -> float."""
    if value is None:
        raise ValueError("leerer Betrag")
    s = str(value).strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not s:
        raise ValueError("leerer Betrag")
    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-+")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # deutsch: 1.234,56
        else:
            s = s.replace(",", "")                     # englisch: 1,234.56
    elif "," in s:
        s = s.replace(",", ".")
    val = float(s)
    return -val if neg else val


def parse_date(value: str) -> str:
    """Verschiedene Datumsformate -> 'YYYY-MM-DD'."""
    s = str(value).strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return pd.to_datetime(s, format=fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")


def normalize(df: pd.DataFrame, col_date: str, col_amount: str,
              col_payee: str | None, col_desc: str | None) -> pd.DataFrame:
    """Gemappte Spalten -> normalisierte Tabelle (date, amount, payee, description).

    Zeilen ohne parsbares Datum/Betrag (Fusszeilen, Zwischensummen) werden verworfen.
    """
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append(
                {
                    "date": parse_date(r[col_date]),
                    "amount": parse_amount(r[col_amount]),
                    "payee": str(r[col_payee]).strip() if col_payee and pd.notna(r.get(col_payee)) else "",
                    "description": str(r[col_desc]).strip() if col_desc and pd.notna(r.get(col_desc)) else "",
                }
            )
        except Exception:
            continue
    return pd.DataFrame(rows)
