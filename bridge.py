"""
Stillhalter AI App — TWS Bridge
================================
Startet automatisch einen SSH-Tunnel (serveo.net) zu TWS.
Kein Account, kein Download, keine Kreditkarte nötig — SSH ist auf jedem Mac.

Starten:
  python3 bridge.py

Dann in der App Seite 14 → "Über ngrok" → Host + Port aus dieser Ausgabe eintragen.
"""

import sys
import subprocess
import re
import signal
import socket
import time

TWS_PORT = 7497   # Paper Trading TWS (Live: 7496)

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          STILLHALTER AI APP — TWS Bridge                 ║
╠══════════════════════════════════════════════════════════╣
║  Verbindet deine App auf Railway mit TWS auf diesem Mac  ║
╚══════════════════════════════════════════════════════════╝
"""


def _check_tws() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", TWS_PORT), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


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

    print("🚀 Starte Tunnel über serveo.net...")

    # SSH-Key sicherstellen
    import os
    key_path = os.path.expanduser("~/.ssh/id_rsa")
    if not os.path.exists(key_path):
        print("   🔑 Kein SSH-Key gefunden — wird automatisch erstellt...", end=" ", flush=True)
        subprocess.run(
            ["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", key_path, "-N", ""],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("✅")

    # SSH-Tunnel starten
    cmd = [
        "ssh", "-tt",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "PasswordAuthentication=no",
        "-R", f"0:localhost:{TWS_PORT}",
        "serveo.net"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def _cleanup(signum=None, frame=None):
        print("\n\n🛑 Bridge wird beendet...")
        proc.terminate()
        print("✅ Tunnel geschlossen.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Auf Tunnel-URL warten
    host = None
    port = None
    start = time.time()

    for line in proc.stdout:
        line = line.strip()

        # URL erkennen: "Forwarding TCP connections from tcp://serveo.net:XXXXX"
        match = re.search(r"tcp://([^:]+):(\d+)", line)
        if match:
            host = match.group(1)
            port = match.group(2)
            break

        # Timeout nach 20 Sekunden
        if time.time() - start > 20:
            print("❌ Timeout — kein Tunnel erhalten.")
            print("   serveo.net ist möglicherweise nicht erreichbar.")
            print("   Bitte nochmal versuchen oder ngrok.com nutzen.\n")
            proc.terminate()
            sys.exit(1)

    if not host or not port:
        print("❌ Keine Tunnel-URL erhalten.")
        proc.terminate()
        sys.exit(1)

    # Erfolgsmeldung
    print("✅ Tunnel aktiv!\n")
    print("═" * 56)
    print(f"  🔗 In der App eintragen (Seite 14 → 'Über ngrok'):")
    print(f"")
    print(f"     Host:  {host}")
    print(f"     Port:  {port}")
    print(f"")
    print("═" * 56)
    print(f"\n  ⚡ TWS-Port {TWS_PORT} → tcp://{host}:{port}")
    print(f"  🔒 Tunnel läuft bis du dieses Fenster schließt")
    print(f"\n  Zum Beenden: Ctrl+C\n")

    # Prozess am Leben halten
    proc.wait()
    print("\n⚠️  Tunnel wurde unerwartet beendet. Bitte neu starten.\n")


if __name__ == "__main__":
    main()
