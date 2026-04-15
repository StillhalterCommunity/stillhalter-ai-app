"""
Stillhalter AI App — TWS Bridge
================================
Startet einen lokalen HTTP-Server + SSH-Tunnel über localhost.run.
Kein Account, kein Download, keine Kreditkarte, keine Authentifizierung.

Starten:
  python3 bridge.py

Dann in der App Seite 14 → "Über Tunnel" → die angezeigte URL eintragen.
"""

import sys
import subprocess
import re
import signal
import socket
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

TWS_PORT   = 7497    # Paper Trading TWS (Live: 7496)
BRIDGE_PORT = 8765   # Lokaler HTTP-Port für die Bridge

# Einfacher API-Key zum Schutz (kannst du ändern)
API_KEY = "stillhalter-bridge"

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          STILLHALTER AI APP — TWS Bridge                 ║
╚══════════════════════════════════════════════════════════╝
"""


def _check_tws() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", TWS_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def _get_ib():
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    from ib_insync import IB
    return IB()


class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Kein Logging-Spam

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ping":
            self._send_json(200, {"status": "ok", "tws": _check_tws()})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        # Auth prüfen
        if self.headers.get("X-API-Key") != API_KEY:
            self._send_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if self.path == "/order":
            self._handle_order(body)
        elif self.path == "/cancel":
            self._handle_cancel(body)
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_order(self, body: dict):
        try:
            from ib_insync import Option, LimitOrder, MarketOrder
            ib = _get_ib()
            ib.connect("127.0.0.1", TWS_PORT, clientId=43, timeout=5)

            contract = Option(
                symbol=body["ticker"],
                lastTradeDateOrContractMonth=body["expiration"],
                strike=float(body["strike"]),
                right=body["right"],
                exchange="SMART",
                currency="USD",
                multiplier="100",
            )
            ib.qualifyContracts(contract)

            if body.get("order_type", "LMT") == "LMT":
                order = LimitOrder(
                    action=body["action"],
                    totalQuantity=int(body["quantity"]),
                    lmtPrice=float(body["limit_price"]),
                    transmit=False,
                    tif="DAY",
                )
            else:
                order = MarketOrder(
                    action=body["action"],
                    totalQuantity=int(body["quantity"]),
                    transmit=False,
                    tif="DAY",
                )

            trade = ib.placeOrder(contract, order)
            ib.sleep(1)
            order_id = trade.order.orderId
            ib.disconnect()

            print(f"  ✅ Order platziert: {body['action']} {body['quantity']}x "
                  f"{body['ticker']} {body['strike']}{body['right']} → ID {order_id}")
            self._send_json(200, {"order_id": order_id, "status": "Held"})

        except Exception as e:
            print(f"  ❌ Order-Fehler: {e}")
            self._send_json(500, {"error": str(e)})

    def _handle_cancel(self, body: dict):
        try:
            ib = _get_ib()
            ib.connect("127.0.0.1", TWS_PORT, clientId=43, timeout=5)
            trades = ib.openTrades()
            target = next((t for t in trades if t.order.orderId == body["order_id"]), None)
            if target:
                ib.cancelOrder(target.order)
                ib.sleep(0.5)
                ib.disconnect()
                self._send_json(200, {"status": "cancelled"})
            else:
                ib.disconnect()
                self._send_json(404, {"error": "order not found"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})


def _start_http_server():
    server = HTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
    server.serve_forever()


def main():
    print(BANNER)

    # TWS prüfen
    print(f"🔍 Prüfe TWS auf Port {TWS_PORT}...", end=" ", flush=True)
    if _check_tws():
        print("✅ TWS läuft")
    else:
        print("❌ TWS nicht gefunden!")
        print(f"\n   Bitte TWS starten (Paper Trading, Port {TWS_PORT})")
        print("   Dann dieses Skript erneut starten.\n")
        sys.exit(1)

    # ib_insync prüfen
    try:
        import ib_insync  # noqa
    except ImportError:
        print("❌ ib_insync nicht installiert.")
        print("   Bitte ausführen: pip3 install ib_insync\n")
        sys.exit(1)

    # HTTP-Server starten
    t = threading.Thread(target=_start_http_server, daemon=True)
    t.start()
    print(f"🌐 HTTP-Server läuft auf Port {BRIDGE_PORT}")

    # SSH-Tunnel über localhost.run (kein Account nötig)
    print("🚀 Starte Tunnel über localhost.run...")
    cmd = [
        "ssh", "-tt",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-R", f"80:localhost:{BRIDGE_PORT}",
        "nokey@localhost.run"
    ]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def _cleanup(signum=None, frame=None):
        print("\n\n🛑 Bridge wird beendet...")
        proc.terminate()
        print("✅ Fertig.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Auf Tunnel-URL warten
    # localhost.run nutzt seit 2024 .lhr.life als Domain (alt: .localhost.run)
    tunnel_url = None
    start = time.time()
    for line in proc.stdout:
        line = line.strip()
        match = re.search(
            r"https://(?!admin\.localhost\.run)([\w\-]+\.lhr\.life|[\w\-]+\.localhost\.run)",
            line
        )
        if match:
            tunnel_url = match.group(0)
            break
        if time.time() - start > 30:
            break

    if not tunnel_url:
        print("❌ Kein Tunnel erhalten. Bitte nochmal versuchen.\n")
        proc.terminate()
        sys.exit(1)

    print("✅ Tunnel aktiv!\n")
    print("═" * 58)
    print(f"  🔗 In der App eintragen (Seite 14 → 'Über Tunnel'):")
    print(f"")
    print(f"     Tunnel-URL:  {tunnel_url}")
    print(f"     API-Key:     {API_KEY}")
    print(f"")
    print("═" * 58)
    print(f"\n  🔒 Fenster offen lassen solange du traden willst")
    print(f"  Zum Beenden: Ctrl+C\n")

    proc.wait()
    print("\n⚠️  Tunnel beendet. Bitte neu starten.\n")


if __name__ == "__main__":
    main()
