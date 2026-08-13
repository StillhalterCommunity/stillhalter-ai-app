"""Stillhalter-Positionsbewertung — zentrale Logik.

Aus pages/07_Trade_Management.py extrahiert, damit auch "Mein Depot"
(Seite 22) dieselben Empfehlungen nutzen kann. Bewertet eine einzelne
Optionsposition (Short = Stillhalter-Regeln, Long = Schutz-Logik) und
liefert Empfehlung, Farbe und Detail-Punkte.
"""

from __future__ import annotations

import math
from datetime import datetime

import streamlit as st
import yfinance as yf

from data.fetcher import (
    fetch_price_history, fetch_stock_info, calculate_dte, fetch_earnings_date,
)
from analysis.technicals import analyze_technicals


@st.cache_data(ttl=300, show_spinner=False)
def _get_option_price(ticker, typ, strike, verfall_str):
    """Holt aktuellen Mid-Preis der Option von yfinance."""
    try:
        stock = yf.Ticker(ticker)
        exps  = stock.options
        if not exps:
            return None
        target   = datetime.strptime(verfall_str, "%Y-%m-%d").date()
        best_exp = min(exps, key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - target).days))
        chain    = stock.option_chain(best_exp)
        df       = chain.puts if typ == "PUT" else chain.calls
        if df.empty:
            return None
        row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
        bid  = float(row["bid"].iloc[0] or 0)
        ask  = float(row["ask"].iloc[0] or 0)
        last = float(row["lastPrice"].iloc[0] or 0)
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 2)
        return round(last, 2) if last > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def evaluate_position(
    ticker,
    typ,
    strike,
    verfall_str,
    menge,
    praemie_ein,
    praemie_akt_pre=None,   # vorberechneter aktueller Preis (aus IBKR)
    pnl_usd_pre=None,       # vorberechneter P&L in USD (aus IBKR)
):
    """
    Bewertet eine einzelne Stillhalter-Position nach Strategie-Regeln.
    Wenn praemie_akt_pre/pnl_usd_pre gesetzt, werden diese direkt genutzt (IBKR-Import).
    """
    result = {
        "ticker":           ticker,
        "typ":              typ,
        "strike":           strike,
        "verfall":          verfall_str,
        "menge":            menge,
        "praemie_ein":      praemie_ein,
        "kurs":             None,
        "praemie_aktuell":  praemie_akt_pre,   # direkt aus IBKR oder via yfinance
        "dte":              None,
        "pnl_pct":          None,
        "pnl_usd":          pnl_usd_pre,       # direkt aus IBKR oder berechnet
        "otm_pct":          None,
        "trend":            None,
        "macd":             None,
        "stoch":            None,
        "earnings":         None,
        "empfehlung":       "–",
        "empfehlung_color": "#888",
        "risiko_score":     50,
        "details":          [],
    }

    kontrakte = abs(menge)
    is_short  = menge < 0

    # ── Aktueller Kurs ────────────────────────────────────────────────────────
    try:
        info = fetch_stock_info(ticker)
        kurs = info.get("price")
        if kurs:
            result["kurs"] = round(float(kurs), 2)
    except Exception:
        pass

    # ── DTE ───────────────────────────────────────────────────────────────────
    try:
        dte = calculate_dte(verfall_str)
        result["dte"] = max(0, dte)
    except Exception:
        pass

    # ── Aktueller Optionspreis (nur wenn nicht aus IBKR) ─────────────────────
    if praemie_akt_pre is None:
        try:
            p_aktuell = _get_option_price(ticker, typ, strike, verfall_str)
            result["praemie_aktuell"] = p_aktuell
        except Exception:
            pass

    # ── P&L berechnen ────────────────────────────────────────────────────────
    p_ein = praemie_ein
    p_akt = result["praemie_aktuell"]

    if pnl_usd_pre is not None:
        # IBKR liefert P&L direkt — nur % berechnen
        result["pnl_usd"] = pnl_usd_pre
        if p_ein and p_ein > 0 and kontrakte > 0:
            max_profit = p_ein * 100 * kontrakte
            result["pnl_pct"] = round(pnl_usd_pre / max_profit * 100, 1)
    elif p_ein and p_akt is not None:
        if is_short:
            pnl_per_share = p_ein - p_akt
        else:
            pnl_per_share = p_akt - p_ein
        result["pnl_pct"] = round(pnl_per_share / p_ein * 100, 1) if p_ein > 0 else None
        result["pnl_usd"] = round(pnl_per_share * 100 * kontrakte, 0)

    # ── OTM% berechnen ────────────────────────────────────────────────────────
    kurs = result["kurs"]
    if kurs and strike > 0:
        if typ == "PUT":
            otm = (kurs - strike) / kurs * 100
        else:
            otm = (strike - kurs) / kurs * 100
        result["otm_pct"] = round(otm, 1)
        # OTM in USD (absoluter Abstand)
        result["otm_usd"] = round(abs(kurs - strike), 2)

    # ── Technische Analyse ────────────────────────────────────────────────────
    try:
        hist = fetch_price_history(ticker, period="6mo")
        if hist is not None and not hist.empty:
            tech = analyze_technicals(hist)
            if tech:
                result["trend"] = tech.trend
                result["macd"]  = tech.sc_macd.signal_strength if tech.sc_macd else None
                result["stoch"] = tech.dual_stoch.signal_strength if tech.dual_stoch else None
                if tech.support_levels and kurs:
                    below = [s for s in tech.support_levels if s < kurs]
                    if below:
                        result["nearest_support"] = max(below)
    except Exception:
        pass

    # ── Earnings ──────────────────────────────────────────────────────────────
    try:
        earn_str = fetch_earnings_date(ticker)
        if earn_str:
            earn_dte = calculate_dte(earn_str)
            dte_val  = result["dte"] or 999
            if 0 <= earn_dte <= dte_val:
                result["earnings"] = earn_str
    except Exception:
        pass

    # ── Empfehlung erzeugen ───────────────────────────────────────────────────
    details     = []
    risk_points = 0

    dte_val = result["dte"]
    pnl_pct = result["pnl_pct"]
    pnl_usd = result["pnl_usd"]
    otm_pct = result["otm_pct"]
    otm_usd = result.get("otm_usd")
    trend   = result["trend"]
    macd    = result["macd"]

    # ══════════════════════════════════════════════════════════════════════════
    # LONG POSITIONEN — vollständig separate Logik
    # (gekaufte Optionen: Schutzpositionen, Spread-Legs, spekulative Longs)
    # ══════════════════════════════════════════════════════════════════════════
    if not is_short:
        result["is_long"] = True

        # Info-Label
        details.append(("📋", f"Long {typ} — gekaufte Option (Absicherung oder Spread-Leg)"))

        # DTE für Long: OTM + verfallend = GUT (Schutz war nicht nötig)
        if dte_val is not None:
            if dte_val <= 0:
                details.append(("📋", "Option abgelaufen — Prämie verfallen (einkalkulierte Absicherungskosten)"))
            elif dte_val <= 14:
                if otm_pct is not None and otm_pct >= 5:
                    details.append(("✅", f"Noch {dte_val} Tage bis Verfall — Option OTM: verfällt planmäßig wertlos (Schutz war nicht nötig)"))
                elif otm_pct is not None and otm_pct < 0:
                    details.append(("💰", f"Noch {dte_val} Tage bis Verfall — Option ITM: Schutz greift! Inneren Wert sichern."))
                else:
                    details.append(("🕐", f"Noch {dte_val} Tage bis Verfall — nahe am Strike: Entwicklung beobachten"))
            else:
                details.append(("✅", f"{dte_val} Tage bis Verfall — ausreichend Zeit"))

        # P&L für Long: Verlust bei OTM-Verfall ist NORMAL/ERWARTET
        if pnl_pct is not None:
            pnl_usd_str = f" ({'+' if (pnl_usd or 0) >= 0 else ''}{pnl_usd:.0f} USD)" if pnl_usd is not None else ""
            if pnl_pct >= 50:
                details.append(("💰", f"Option im Plus +{pnl_pct:.0f}%{pnl_usd_str} — Gewinnmitnahme möglich"))
            elif pnl_pct >= 0:
                details.append(("✅", f"Option leicht im Plus +{pnl_pct:.0f}%{pnl_usd_str}"))
            elif pnl_pct >= -60:
                if otm_pct is not None and otm_pct >= 5:
                    details.append(("✅", f"Absicherungskosten {pnl_pct:.0f}%{pnl_usd_str} — erwartet bei OTM-Option (Schutz nicht benötigt)"))
                else:
                    details.append(("🟡", f"Option {pnl_pct:.0f}%{pnl_usd_str} — normaler Zeitwertverlust"))
            else:
                details.append(("⚠️", f"Hohe Absicherungskosten {pnl_pct:.0f}%{pnl_usd_str} — Strategie prüfen"))

        # OTM für Long: ITM = gut (Schutz greift)
        if otm_pct is not None:
            otm_usd_str = f" ({otm_usd:.2f} USD Abstand)" if otm_usd else ""
            if otm_pct < 0:
                details.append(("🛡️", f"Option ITM {abs(otm_pct):.1f}%{otm_usd_str} — Schutzstellung greift!"))
            elif otm_pct < 5:
                details.append(("🕐", f"Option nahe am Strike ({otm_pct:.1f}% OTM){otm_usd_str} — beobachten"))
            else:
                details.append(("✅", f"Option {otm_pct:.1f}% OTM{otm_usd_str} — verfällt voraussichtlich wertlos"))

        # Trend für Long: bearish ist GUT für Long PUT (umgekehrte Logik)
        if trend:
            if typ == "PUT":
                if trend == "bearish":
                    details.append(("✅", "Trend bearisch — vorteilhaft für Long PUT (Schutz wächst im Wert)"))
                elif trend == "bullish":
                    details.append(("📋", "Trend bullisch — Long PUT verliert an Wert (Schutz nicht benötigt, planmäßig)"))
                else:
                    details.append(("🟡", "Trend seitwärts — neutral für Long PUT"))
            else:  # CALL
                if trend == "bullish":
                    details.append(("✅", "Trend bullisch — vorteilhaft für Long CALL"))
                elif trend == "bearish":
                    details.append(("📋", "Trend bearisch — Long CALL verliert an Wert"))

        # MACD für Long
        if macd:
            macd_long_map = {
                "strong_bull": ("✅", "SC MACD Pro stark bullisch") if typ == "CALL" else ("📋", "SC MACD Pro stark bullisch — Long PUT verliert Wert"),
                "bull":        ("✅", "SC MACD Pro bullisch") if typ == "CALL" else ("📋", "SC MACD Pro bullisch"),
                "neutral":     ("🟡", "SC MACD Pro neutral"),
                "bear":        ("✅", "SC MACD Pro bearisch — Long PUT gewinnt Wert") if typ == "PUT" else ("📋", "SC MACD Pro bearisch"),
                "strong_bear": ("✅", "SC MACD Pro stark bearisch — Long PUT greift") if typ == "PUT" else ("📋", "SC MACD Pro stark bearisch"),
            }
            if macd in macd_long_map:
                details.append(macd_long_map[macd])

        # Earnings
        if result["earnings"]:
            details.append(("ℹ️", f"Earnings innerhalb Laufzeit: {result['earnings']} → IV-Anstieg begünstigt Long-Option"))

        # Kein Roll für Long OTM Positionen
        # Gesamtempfehlung für Long
        result["risiko_score"] = 0
        result["details"] = details

        if dte_val is not None and dte_val <= 0:
            result["empfehlung"]       = "📋 Abgelaufen (Kosten einkalkuliert)"
            result["empfehlung_color"] = "#888"
        elif otm_pct is not None and otm_pct < 0:
            result["empfehlung"]       = "🛡️ Schutz greift (ITM)"
            result["empfehlung_color"] = "#60a5fa"
        elif pnl_pct is not None and pnl_pct >= 50:
            result["empfehlung"]       = "💰 Gewinnmitnahme"
            result["empfehlung_color"] = "#22c55e"
        elif otm_pct is not None and otm_pct >= 5 and dte_val is not None and dte_val <= 14:
            result["empfehlung"]       = "✅ Schutz läuft planmäßig aus"
            result["empfehlung_color"] = "#22c55e"
        else:
            result["empfehlung"]       = "📋 Halten (Absicherung)"
            result["empfehlung_color"] = "#888"

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # SHORT POSITIONEN — Stillhalter-Logik
    # Klares Statusmodell: Halten / Schließen / Rollen / Einbuchen / Abgelaufen
    # ══════════════════════════════════════════════════════════════════════════

    # ── ATH (52-Wochen-Hoch als Proxy für "günstige Einbuchung") ─────────────
    ath = None
    try:
        info = fetch_stock_info(ticker)
        ath  = info.get("week52High") or info.get("fiftyTwoWeekHigh")
        if ath:
            ath = float(ath)
            result["ath"] = ath
    except Exception:
        pass

    # ── Theta-Verlauf: Ist der Zeitwertverfall im Plan? ──────────────────────
    # Modell: Theta ist konvex (beschleunigt zur Laufzeit-Ende)
    # Approximation: verbleibender Wert ∝ sqrt(DTE_rest / DTE_gesamt)
    # Annahme: typischer Einstieg bei 45 DTE
    theta_status    = "unbekannt"
    expected_pnl    = None
    theta_label     = ""
    assumed_dte_ein = 45   # typischer Einstieg

    if dte_val is not None and praemie_ein > 0 and pnl_pct is not None:
        total_dte = max(assumed_dte_ein, dte_val + 5)  # mindestens 5 Tage Laufzeit vergangen
        elapsed_frac = max(0.0, (total_dte - dte_val) / total_dte)
        expected_pnl = round((1 - math.sqrt(max(0, 1 - elapsed_frac))) * 100, 1)

        if pnl_pct >= expected_pnl * 1.25:
            theta_status = "schnell"
            theta_label  = f"Zeitwert verfällt schneller als erwartet (+{pnl_pct:.0f}% vs. erwartet {expected_pnl:.0f}%) — günstige Entwicklung"
        elif pnl_pct <= expected_pnl * 0.65:
            theta_status = "langsam"
            theta_label  = f"Zeitwert verfällt langsamer als erwartet ({pnl_pct:.0f}% vs. erwartet {expected_pnl:.0f}%) — IV oder Kurs wirkt gegen die Position"
        else:
            theta_status = "planmäßig"
            theta_label  = f"Zeitwert verfällt planmäßig ({pnl_pct:.0f}% vereinnahmt, erwartet ~{expected_pnl:.0f}%) — Position im Rahmen"

    result["theta_status"] = theta_status
    result["expected_pnl"] = expected_pnl

    # ── Details aufbauen (maximal 5 klare Punkte) ────────────────────────────
    pnl_usd_str = f" ({'+' if (pnl_usd or 0) >= 0 else ''}{pnl_usd:.0f} USD)" if pnl_usd is not None else ""

    # 1. Theta-Verlauf (wichtigster Indikator)
    if theta_label:
        theta_icon = "✅" if theta_status == "schnell" else ("⚠️" if theta_status == "langsam" else "🟡")
        details.append((theta_icon, theta_label))

    # 2. OTM-Abstand (Sicherheitszone)
    if otm_pct is not None:
        otm_usd_str = f" ({otm_usd:.2f} USD Abstand)" if otm_usd else ""
        if otm_pct >= 15:
            details.append(("✅", f"{otm_pct:.1f}% OTM{otm_usd_str} — sicherer Puffer"))
        elif otm_pct >= 8:
            details.append(("🟡", f"{otm_pct:.1f}% OTM{otm_usd_str} — Puffer vorhanden, beobachten"))
        elif otm_pct >= 3:
            details.append(("⚠️", f"Nur {otm_pct:.1f}% OTM{otm_usd_str} — Strike in Reichweite! Delta ist gestiegen."))
        elif otm_pct >= 0:
            details.append(("🔴", f"Sehr nah am Geld ({otm_pct:.1f}% OTM){otm_usd_str} — Entscheidung nötig: Rollen oder Einbuchen"))
        else:
            details.append(("🔴", f"Im Geld ({abs(otm_pct):.1f}% ITM){otm_usd_str} — Einbuchung droht"))

    # 3. Trend — kurz und relevant
    if trend:
        if typ == "PUT":
            if trend == "bullish":
                details.append(("✅", "Trend bullisch — Aktie bewegt sich vom Strike weg"))
            elif trend == "bearish":
                details.append(("⚠️", "Trend bearisch — Aktie bewegt sich Richtung Strike"))
        else:
            if trend == "bearish":
                details.append(("✅", "Trend bearisch — Aktie bewegt sich vom Strike weg"))
            elif trend == "bullish":
                details.append(("⚠️", "Trend bullisch — Aktie bewegt sich Richtung Strike"))

    # 4. Earnings-Warnung
    if result["earnings"]:
        details.append(("⚠️", f"Earnings {result['earnings']} innerhalb der Laufzeit — IV-Anstieg kann Option verteuern"))

    # 5. Einbuchungs-Analyse (wenn nahe am Geld oder ITM)
    if ath and kurs and (otm_pct is not None and otm_pct < 10):
        pct_below_ath = round((ath - strike) / ath * 100, 1)
        if typ == "PUT":
            if pct_below_ath >= 40:
                details.append((
                    "📦",
                    f"Strike @{strike:.0f} liegt {pct_below_ath:.0f}% unter dem 52-Wochen-Hoch ({ath:.2f}) — "
                    f"Einbuchung zu einem stark vergünstigten Kurs attraktiv."
                ))
            elif pct_below_ath >= 20:
                details.append((
                    "📦",
                    f"Strike @{strike:.0f} liegt {pct_below_ath:.0f}% unter dem 52-Wochen-Hoch ({ath:.2f}) — "
                    f"Einbuchung möglicherweise akzeptabel (Aktie kaufen zu Rabattpreis)."
                ))
            else:
                details.append((
                    "🔄",
                    f"Strike @{strike:.0f} nur {pct_below_ath:.0f}% unter 52W-Hoch ({ath:.2f}) — "
                    f"Einbuchung wenig attraktiv → Rollen bevorzugen."
                ))

    # ── Roll-Angabe bei Bedarf ────────────────────────────────────────────────
    if otm_pct is not None and otm_pct < 5 and dte_val is not None and 0 < dte_val <= 21:
        target_dte = (dte_val or 0) + 35
        if otm_pct < 0:
            new_strike = round(strike * (0.90 if typ == "PUT" else 1.10) / 5) * 5
            details.append((
                "🔄",
                f"Roll-Option: {typ} von @{strike:.0f} auf @{new_strike:.0f} "
                f"({'−10%' if typ=='PUT' else '+10%'}) und ~{target_dte} Tage Laufzeit — "
                f"nur wenn Netto-Kredit positiv (Einnahme > Ausgabe)."
            ))
        else:
            details.append((
                "🔄",
                f"Roll-Option: {typ} @{strike:.0f} gleicher Strike auf ~{target_dte} Tage weiter rollen — "
                f"mehr Zeit kaufen, zusätzliche Prämie einsammeln."
            ))

    # ── Gesamtempfehlung — 5 klare Status, keine Überschneidung ─────────────
    result["risiko_score"] = 0   # nicht mehr verwendet, aber Feld bleibt kompatibel
    result["details"]      = details

    # STATUS-LOGIK (Priorität von oben nach unten):
    if dte_val is not None and dte_val <= 0:
        # Abgelaufen — kein Handlungsbedarf mehr, Status nur informativ
        if otm_pct is not None and otm_pct >= 0:
            result["empfehlung"]       = "📋 Abgelaufen · wertlos verfallen"
            result["empfehlung_color"] = "#22c55e"
        else:
            result["empfehlung"]       = "📋 Abgelaufen · Eingebucht (bitte anpassen)"
            result["empfehlung_color"] = "#60a5fa"

    elif otm_pct is not None and otm_pct < 0:
        # ITM — erst bei kurzer Restlaufzeit handeln, sonst Gegenbewegung abwarten
        if dte_val is not None and dte_val > 21:
            result["empfehlung"]       = "👀 ITM — Gegenbewegung abwarten"
            result["empfehlung_color"] = "#f59e0b"
        elif ath and typ == "PUT":
            pct_below = (ath - strike) / ath * 100
            if pct_below >= 30:
                result["empfehlung"]       = "📦 Einbuchen prüfen (attraktiver Kurs)"
                result["empfehlung_color"] = "#60a5fa"
            else:
                result["empfehlung"]       = "🔄 Rollen oder Einbuchen"
                result["empfehlung_color"] = "#f97316"
        else:
            result["empfehlung"]       = "🔄 Rollen oder Einbuchen"
            result["empfehlung_color"] = "#f97316"

    elif otm_pct is not None and otm_pct < 5:
        # Sehr nah am Geld — Alarm
        result["empfehlung"]       = "⚠️ Am Geld — Entscheidung nötig"
        result["empfehlung_color"] = "#f59e0b"

    elif pnl_pct is not None and pnl_pct >= 70:
        # 70%-Ziel erreicht
        result["empfehlung"]       = "💰 70%-Ziel erreicht — schließen"
        result["empfehlung_color"] = "#22c55e"

    elif pnl_pct is not None and pnl_pct >= 50 and theta_status == "schnell":
        # Überdurchschnittlicher Zerfall — frühzeitig schließen lohnt
        result["empfehlung"]       = "💰 Schneller Zerfall — Schließen prüfen"
        result["empfehlung_color"] = "#22c55e"

    elif otm_pct is not None and otm_pct < 8:
        # Puffer wird kleiner — beobachten
        result["empfehlung"]       = "👀 OTM-Abstand gering — beobachten"
        result["empfehlung_color"] = "#f59e0b"

    elif theta_status == "langsam" and (pnl_pct or 0) < 0:
        # Zeitwert läuft langsam UND im Minus — aktiv beobachten
        result["empfehlung"]       = "👀 Unter Plan — beobachten"
        result["empfehlung_color"] = "#60a5fa"

    else:
        result["empfehlung"]       = "✅ Läuft nach Plan"
        result["empfehlung_color"] = "#22c55e"

    return result
