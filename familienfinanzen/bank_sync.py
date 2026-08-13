"""Anbindung an GoCardless Bank Account Data (ehemals Nordigen).

Kostenloser PSD2-Kontoinformationszugang (AIS) fuer ~2.300 europaeische
Banken inkl. deutscher Girokonten und vieler Kreditkarten. Ablauf:

1. Einmalig unter https://bankaccountdata.gocardless.com einen (kostenlosen)
   Account anlegen und Secret ID / Secret Key erzeugen.
2. Beide als Umgebungsvariablen setzen:
      GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY
3. In der App (Seite "Import & Banking") die Bank waehlen -> es entsteht
   eine "Requisition" mit einem Link, ueber den man sich EINMAL bei der
   eigenen Bank anmeldet (PSD2-Zustimmung, gilt i. d. R. 90-180 Tage).
4. Danach koennen Konten und Umsaetze jederzeit per API abgerufen werden —
   die Bank-Zugangsdaten landen NIE in dieser App.
"""

import os
from typing import Optional

import requests

BASE = "https://bankaccountdata.gocardless.com/api/v2"


def _secret(name: str) -> str:
    """Umgebungsvariable oder st.secrets (Streamlit Community Cloud)."""
    val = os.environ.get(name, "")
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def credentials_present() -> bool:
    return bool(_secret("GOCARDLESS_SECRET_ID") and _secret("GOCARDLESS_SECRET_KEY"))


class GoCardlessClient:
    def __init__(self, secret_id: Optional[str] = None, secret_key: Optional[str] = None):
        self.secret_id = secret_id or _secret("GOCARDLESS_SECRET_ID")
        self.secret_key = secret_key or _secret("GOCARDLESS_SECRET_KEY")
        self._token: Optional[str] = None

    # --- intern ---------------------------------------------------------
    def _auth(self) -> str:
        if self._token:
            return self._token
        r = requests.post(
            f"{BASE}/token/new/",
            json={"secret_id": self.secret_id, "secret_key": self.secret_key},
            timeout=30,
        )
        r.raise_for_status()
        self._token = r.json()["access"]
        return self._token

    def _get(self, path: str, **params) -> dict:
        r = requests.get(
            f"{BASE}{path}",
            headers={"Authorization": f"Bearer {self._auth()}"},
            params=params,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict) -> dict:
        r = requests.post(
            f"{BASE}{path}",
            headers={"Authorization": f"Bearer {self._auth()}"},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()

    # --- oeffentliche API -------------------------------------------------
    def institutions(self, country: str = "de") -> list:
        """Alle unterstuetzten Banken eines Landes: [{id, name, ...}]"""
        return self._get("/institutions/", country=country)

    def create_requisition(self, institution_id: str, redirect_url: str, reference: str) -> dict:
        """Startet die Bank-Zustimmung. Ergebnis enthaelt 'link' (Autorisierungs-URL) und 'id'."""
        return self._post(
            "/requisitions/",
            {"redirect": redirect_url, "institution_id": institution_id, "reference": reference},
        )

    def requisition(self, requisition_id: str) -> dict:
        """Status + Liste der freigegebenen Konto-IDs ('accounts')."""
        return self._get(f"/requisitions/{requisition_id}/")

    def account_details(self, account_id: str) -> dict:
        return self._get(f"/accounts/{account_id}/details/").get("account", {})

    def account_balances(self, account_id: str) -> list:
        return self._get(f"/accounts/{account_id}/balances/").get("balances", [])

    def transactions(self, account_id: str, date_from: Optional[str] = None) -> list:
        """Gebuchte Umsaetze, normalisiert auf unser internes Format."""
        params = {"date_from": date_from} if date_from else {}
        data = self._get(f"/accounts/{account_id}/transactions/", **params)
        booked = data.get("transactions", {}).get("booked", [])
        out = []
        for t in booked:
            amount = float(t.get("transactionAmount", {}).get("amount", 0))
            payee = (
                t.get("creditorName")
                or t.get("debtorName")
                or t.get("merchantName")
                or ""
            )
            desc = (
                t.get("remittanceInformationUnstructured")
                or " ".join(t.get("remittanceInformationUnstructuredArray", []) or [])
                or ""
            )
            out.append(
                {
                    "date": t.get("bookingDate") or t.get("valueDate"),
                    "amount": amount,
                    "payee": payee,
                    "description": desc,
                }
            )
        return out
