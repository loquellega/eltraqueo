# SPDX-License-Identifier: GPL-3.0-or-later
"""Punto de entrada: arranca el motor, la interfaz local y abre el navegador."""
from __future__ import annotations

import argparse
import signal
import socket
import sys
import time
import webbrowser

from . import APP_NAME, __version__
from . import config as cfgmod
from .engine import Engine
from .server import serve


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main(argv=None):
    ap = argparse.ArgumentParser(prog=APP_NAME, description="Tracking escénico por cámara → OSC")
    ap.add_argument("--config", help="ruta de config.json (por omisión ~/.eltraqueo/config.json)")
    ap.add_argument("--port", type=int, help="puerto de la interfaz (8765)")
    ap.add_argument("--lan", action="store_true",
                    help="abre la interfaz a la red local (para manejarla desde el teléfono)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--synthetic", action="store_true", help="usa una escena de prueba en vez de cámara")
    ap.add_argument("--osc", help="destino OSC host:puerto (reemplaza la config)")
    ap.add_argument("--idle", action="store_true", help="no arrancar el tracking al abrir")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    a = ap.parse_args(argv)

    cfg = cfgmod.load(a.config)
    if a.synthetic:
        cfg["inputs"] = [{"id": "prueba", "enabled": True,
                          "sensor": {"type": "synthetic", "people": 3, "width": 640, "height": 360},
                          "detector": {"type": "blobs"}, "floor": {"image": [], "world": []},
                          "roi": [0, 0, 1, 1]}]
    if a.osc:
        h, _, p = a.osc.rpartition(":")
        cfg["osc"]["destinations"] = [{"host": h or "127.0.0.1", "port": int(p)}]

    engine = Engine(cfg)
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    port = a.port or int(cfg["ui"].get("port", 8765))
    url = f"http://127.0.0.1:{port}"
    try:
        serve(engine, host, port, a.config, persist=not a.synthetic)
    except OSError:
        # Ya hay un eltraqueo abierto: solo mostramos su interfaz.
        print(f"eltraqueo ya está corriendo en {url}")
        if not a.no_browser:
            webbrowser.open(url)
        return 0
    if not a.idle:
        engine.start()

    print(f"{APP_NAME} {__version__}")
    print(f"  interfaz: {url}")
    if a.lan:
        print(f"  en la red: http://{lan_ip()}:{port}  (sin contraseña: solo en redes de confianza)")
    dests = ", ".join(f"{d['host']}:{d['port']}" for d in cfg["osc"]["destinations"])
    print(f"  OSC → {dests}")
    print("  Ctrl+C para salir")
    if cfg["ui"].get("open_browser", True) and not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    stop = {"v": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))
    try:
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("v", True))
    except Exception:
        pass
    while not stop["v"] and not engine.quit_requested:
        time.sleep(0.2)
    engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
