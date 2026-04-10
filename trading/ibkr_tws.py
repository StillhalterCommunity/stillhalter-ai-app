"""
IBKR TWS Order Management — Stillhalter AI App
===============================================
Verbindet sich mit der lokalen TWS / IB Gateway und platziert
Options-Orders mit transmit=False → Order wird in TWS als "held"
angezeigt. Nutzer muss in TWS manuell auf "Transmit" klicken.

Voraussetzungen:
  - TWS oder IB Gateway läuft lokal
  - API-Zugang in TWS aktiviert: Konfiguration → API → Einstellungen
    ✓ "Enable ActiveX and Socket Clients"
    Port: 7497 (TWS Paper), 7496 (TWS Live), 4002 (Gateway Paper), 4001 (Gateway Live)
  - pip install ib_insync
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ── Verbindungsparameter ──────────────────────────────────────────────────────

TWS_HOST = "127.0.0.1"
TWS_PORT_PAPER = 7497   # TWS Paper Trading
TWS_PORT_LIVE  = 7496   # TWS Live Trading
IB_GW_PORT_PAPER = 4002 # IB Gateway Paper
IB_GW_PORT_LIVE  = 4001 # IB Gateway Live
CLIENT_ID = 42           # Eindeutige Client-ID (kann beliebig gewählt werden)


# ── Datenklassen ──────────────────────────────────────────────────────────────

@dataclass
class IBKRConfig:
    host: str = TWS_HOST
    port: int = TWS_PORT_PAPER
    client_id: int = CLIENT_ID
    readonly: bool = False          # True = nur lesen, kein Handel
    account: str = ""               # leer = Standard-Account


@dataclass
class OptionOrderParams:
    """Parameter für eine einzelne Options-Order."""
    ticker: str                     # z.B. "AAPL"
    expiration: str                 # Format: "YYYYMMDD"
    strike: float                   # Strike-Preis
    right: str                      # "P" für Put, "C" für Call
    action: str                     # "SELL" oder "BUY"
    quantity: int                   # Anzahl Kontrakte (positiv)
    limit_price: float              # Limit-Preis (Prämie pro Aktie)
    order_type: str = "LMT"         # "LMT" oder "MKT"
    exchange: str = "SMART"
    currency: str = "USD"
    multiplier: str = "100"


@dataclass
class PlacedOrder:
    """Ergebnis einer platzierten Order."""
    order_id: int
    ticker: str
    description: str                # z.B. "SELL 1x AAPL 200P 2025-06-20"
    limit_price: float
    quantity: int
    action: str
    status: str = "Held"            # "Held" bis der Nutzer in TWS transmittiert
    transmit: bool = False
    error: Optional[str] = None
    raw_order: object = field(default=None, repr=False)
    raw_contract: object = field(default=None, repr=False)


@dataclass
class AccountSummary:
    account: str = ""
    net_liquidation: float = 0.0
    available_funds: float = 0.0
    buying_power: float = 0.0
    currency: str = "USD"


# ── Verbindung ────────────────────────────────────────────────────────────────

def _get_ib():
    """Importiert ib_insync — gibt None zurück wenn nicht installiert."""
    try:
        from ib_insync import IB
        return IB()
    except ImportError:
        return None


def test_connection(config: IBKRConfig) -> tuple[bool, str]:
    """
    Testet die Verbindung zur TWS.
    Returns (success, message).
    """
    ib = _get_ib()
    if ib is None:
        return False, "ib_insync nicht installiert. Bitte: pip install ib_insync"
    try:
        ib.connect(config.host, config.port, clientId=config.client_id,
                   readonly=config.readonly, timeout=5)
        accounts = ib.managedAccounts()
        ib.disconnect()
        return True, f"Verbunden. Accounts: {', '.join(accounts)}"
    except Exception as e:
        return False, f"Verbindungsfehler: {e}"


def get_account_summary(config: IBKRConfig) -> Optional[AccountSummary]:
    """Holt Kontodaten aus TWS."""
    ib = _get_ib()
    if ib is None:
        return None
    try:
        ib.connect(config.host, config.port, clientId=config.client_id,
                   readonly=True, timeout=5)
        summary_items = ib.accountSummary()
        ib.disconnect()

        result = AccountSummary()
        for item in summary_items:
            if item.tag == "NetLiquidation":
                result.net_liquidation = float(item.value)
                result.currency = item.currency
            elif item.tag == "AvailableFunds":
                result.available_funds = float(item.value)
            elif item.tag == "BuyingPower":
                result.buying_power = float(item.value)
            elif item.tag == "AccountType":
                result.account = item.value
        return result
    except Exception as e:
        logger.error("AccountSummary Fehler: %s", e)
        return None


def get_open_orders(config: IBKRConfig) -> list[dict]:
    """Holt alle offenen / held Orders aus TWS."""
    ib = _get_ib()
    if ib is None:
        return []
    try:
        ib.connect(config.host, config.port, clientId=config.client_id,
                   readonly=True, timeout=5)
        trades = ib.openTrades()
        ib.disconnect()

        result = []
        for trade in trades:
            order = trade.order
            contract = trade.contract
            status = trade.orderStatus.status
            result.append({
                "order_id":    order.orderId,
                "ticker":      contract.symbol,
                "action":      order.action,
                "qty":         order.totalQuantity,
                "limit_price": order.lmtPrice,
                "status":      status,
                "strike":      getattr(contract, "strike", ""),
                "expiry":      getattr(contract, "lastTradeDateOrContractMonth", ""),
                "right":       getattr(contract, "right", ""),
                "sec_type":    contract.secType,
            })
        return result
    except Exception as e:
        logger.error("OpenOrders Fehler: %s", e)
        return []


# ── Order-Platzierung ─────────────────────────────────────────────────────────

def place_option_order(
    params: OptionOrderParams,
    config: IBKRConfig,
) -> PlacedOrder:
    """
    Platziert eine Options-Order in TWS mit transmit=False.

    transmit=False bedeutet:
      - Order wird in TWS als "Held" (gelb) angezeigt
      - Sie wird NICHT an die Börse gesendet
      - Der Nutzer muss in TWS manuell auf "Transmit" klicken
      - Oder: transmit_order() unten aufrufen

    Returns PlacedOrder mit Ergebnisdetails.
    """
    description = (
        f"{params.action} {params.quantity}x {params.ticker} "
        f"{params.strike}{'P' if params.right=='P' else 'C'} "
        f"{params.expiration}"
    )

    ib = _get_ib()
    if ib is None:
        return PlacedOrder(
            order_id=-1,
            ticker=params.ticker,
            description=description,
            limit_price=params.limit_price,
            quantity=params.quantity,
            action=params.action,
            status="Fehler",
            error="ib_insync nicht installiert. Bitte: pip install ib_insync",
        )

    try:
        from ib_insync import Option, LimitOrder, MarketOrder

        ib.connect(config.host, config.port, clientId=config.client_id,
                   readonly=False, timeout=5)

        # Kontrakt definieren
        contract = Option(
            symbol=params.ticker,
            lastTradeDateOrContractMonth=params.expiration,
            strike=params.strike,
            right=params.right,
            exchange=params.exchange,
            currency=params.currency,
            multiplier=params.multiplier,
        )

        # Kontrakt qualifizieren (IBKR braucht conId)
        ib.qualifyContracts(contract)

        # Order erstellen — transmit=False ist entscheidend
        if params.order_type == "LMT":
            order = LimitOrder(
                action=params.action,
                totalQuantity=params.quantity,
                lmtPrice=params.limit_price,
                transmit=False,          # ← Held Order, kein Auto-Transmit
                outsideRth=False,
                tif="DAY",
            )
        else:  # MKT
            order = MarketOrder(
                action=params.action,
                totalQuantity=params.quantity,
                transmit=False,
                tif="DAY",
            )

        # Order platzieren
        trade = ib.placeOrder(contract, order)
        ib.sleep(1)  # kurz warten bis TWS bestätigt

        order_id = trade.order.orderId
        status = trade.orderStatus.status or "PreSubmitted"

        ib.disconnect()

        return PlacedOrder(
            order_id=order_id,
            ticker=params.ticker,
            description=description,
            limit_price=params.limit_price,
            quantity=params.quantity,
            action=params.action,
            status=status,
            transmit=False,
            raw_order=order,
            raw_contract=contract,
        )

    except Exception as e:
        try:
            ib.disconnect()
        except Exception:
            pass
        logger.error("Fehler beim Platzieren: %s", e)
        return PlacedOrder(
            order_id=-1,
            ticker=params.ticker,
            description=description,
            limit_price=params.limit_price,
            quantity=params.quantity,
            action=params.action,
            status="Fehler",
            error=str(e),
        )


def place_strangle_order(
    ticker: str,
    put_params: OptionOrderParams,
    call_params: OptionOrderParams,
    config: IBKRConfig,
) -> list[PlacedOrder]:
    """
    Platziert Short Strangle als zwei Legs (beide transmit=False).
    TWS zeigt beide Orders als Held an.
    """
    results = []
    for params in [put_params, call_params]:
        result = place_option_order(params, config)
        results.append(result)
    return results


def cancel_held_order(order_id: int, config: IBKRConfig) -> tuple[bool, str]:
    """Storniert eine Held-Order in TWS (bevor sie transmittiert wird)."""
    ib = _get_ib()
    if ib is None:
        return False, "ib_insync nicht installiert"
    try:
        ib.connect(config.host, config.port, clientId=config.client_id,
                   readonly=False, timeout=5)
        # Offene Orders holen und die richtige stornieren
        trades = ib.openTrades()
        target = next((t for t in trades if t.order.orderId == order_id), None)
        if target is None:
            ib.disconnect()
            return False, f"Order {order_id} nicht gefunden"
        ib.cancelOrder(target.order)
        ib.sleep(0.5)
        ib.disconnect()
        return True, f"Order {order_id} storniert"
    except Exception as e:
        try:
            ib.disconnect()
        except Exception:
            pass
        return False, str(e)
