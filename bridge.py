"""
Stillhalter AI App — TWS Bridge
================================
Startet automatisch einen ngrok-Tunnel zu TWS und zeigt die Verbindungsdaten an.

Einmalige Installation:
  pip3 install pyngrok

Starten:
  python3 bridge.py

Dann in der App Seite 14 → "Über ngrok" → Host + Port aus dieser Ausgabe eintragen.
"""

import sys
import time
import signal

# ── pyngrok prüfen ────────────────────────────────────────────────────────────
try:
    from pyngrok import ngrok, conf, exception as ngrok_exc
except ImportError:
    print("\n⚠️  pyngrok nicht installiert. Bitte einmalig ausführen:")
    print("   pip3 install pyngrok\n")
    sys.exit(1)

# ── Konfiguration ─────────────────────────────────────────────────────────────
TWS_PORT   = 7497   # Paper Trading TWS
NGROK_AUTH = ""     # Optional: ngrok Auth-Token (ngrok.com → kostenloses Konto)
                    # Ohne Token: Tunnel läuft, aber mit Verbindungslimit

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          STILLHALTER AI APP — TWS Bridge                 ║
╠══════════════════════════════════════════════════════════╣
║  Verbindet deine App auf Railway mit TWS auf diesem Mac  ║
╚══════════════════════════════════════════════════════════╝
"""

def _check_tws_running() -> bool:
    """Prüft ob TWS auf dem konfigurierten Port lauscht."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", TWS_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def _cleanup(tunnel, signum=None, frame=None):
    """Tunnel sauber schließen beim Beenden."""
    print("\n\n🛑 Bridge wird beendet...")
    try:
        ngrok.disconnect(tunnel.public_url)
        ngrok.kill()
    except Exception:
        pass
    print("✅ Tunnel geschlossen. Tschüss!\n")
    sys.exit(0)


def main():
    print(BANNER)

    # TWS-Status prüfen
    print(f"🔍 Prüfe TWS auf Port {TWS_PORT}...", end=" ", flush=True)
    if _check_tws_running():
        print("✅ TWS läuft")
    else:
        print("❌ TWS nicht gefunden!")
        print(f"\n   Bitte TWS starten (Paper Trading, Port {TWS_PORT})")
        print("   Dann dieses Skript erneut starten.\n")
        sys.exit(1)

    # ngrok Auth-Token setzen falls vorhanden
    if NGROK_AUTH:
        conf.get_default().auth_token = NGROK_AUTH

    # Tunnel starten
    print("🚀 Starte ngrok-Tunnel...", end=" ", flush=True)
    try:
        tunnel = ngrok.connect(TWS_PORT, "tcp")
    except ngrok_exc.PyngrokNgrokError as e:
        if "auth" in str(e).lower() or "token" in str(e).lower():
            print("\n\n⚠️  ngrok Auth-Token fehlt oder ungültig.")
            print("   1. Kostenlosen Account auf ngrok.com erstellen")
            print("   2. Auth-Token kopieren")
            print(f"   3. In bridge.py Zeile 'NGROK_AUTH = \"\"' deinen Token eintragen\n")
        else:
            print(f"\n❌ ngrok Fehler: {e}\n")
        sys.exit(1)

    # URL parsen
    public_url = tunnel.public_url  # z.B. tcp://0.tcp.eu.ngrok.io:15432
    host_port  = public_url.replace("tcp://", "")
    host, port = host_port.rsplit(":", 1)

    # Ctrl+C abfangen
    signal.signal(signal.SIGINT, lambda s, f: _cleanup(tunnel, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: _cleanup(tunnel, s, f))

    # Verbindungsdaten anzeigen
    print("✅ Tunnel aktiv!\n")
    print("═" * 56)
    print(f"  🔗 In der App eintragen (Seite 14 → 'Über ngrok'):")
    print(f"")
    print(f"     Host:  {host}")
    print(f"     Port:  {port}")
    print(f"")
    print("═" * 56)
    print(f"\n  ⚡ TWS-Port {TWS_PORT} → {public_url}")
    print(f"  🔒 Tunnel läuft bis du dieses Fenster schließt")
    print(f"\n  Zum Beenden: Ctrl+C\n")

    # Alive-Status alle 30 Sekunden ausgeben
    counter = 0
    while True:
        time.sleep(30)
        counter += 1
        mins = counter * 30 // 60
        secs = (counter * 30) % 60
        print(f"  ⏱  Aktiv seit {mins}:{secs:02d} Min  |  {public_url}", flush=True)


if __name__ == "__main__":
    main()
