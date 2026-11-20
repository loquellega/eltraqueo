# SPDX-License-Identifier: GPL-3.0-or-later
"""Interfaz local: HTTP sencillo (sin dependencias) + vista previa MJPEG."""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, config as cfgmod
from .detectors import LABELS
from .sensors import list_cameras


def ui_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    p = base / "eltraqueo" / "ui"
    return p if p.exists() else Path(__file__).resolve().parent / "ui"


def make_handler(engine, cfg_path, persist=True):
    class H(BaseHTTPRequestHandler):
        server_version = f"eltraqueo/{__version__}"

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                data = (ui_dir() / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path == "/api/state":
                st = engine.state()
                st["version"] = __version__
                self._json(st)
            elif path == "/api/config":
                self._json(engine.cfg)
            elif path == "/api/cameras":
                self._json({"cameras": list_cameras(), "detectors": LABELS})
            elif path.startswith("/preview/"):
                self._mjpeg(path.split("/")[-1].removesuffix(".mjpg"))
            else:
                self.send_error(404)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except Exception:
                return self._json({"error": "json inválido"}, 400)
            if path == "/api/config":
                engine.apply_config(cfgmod.deep_merge(cfgmod.DEFAULT, body))
                p = cfgmod.save(engine.cfg, cfg_path) if persist else None
                self._json({"ok": True, "saved": str(p) if p else ""})
            elif path == "/api/action":
                name = body.get("name", "")
                if name == "start":
                    engine.start(); msg = "en vivo"
                elif name == "stop":
                    engine.stop(); msg = "detenido"
                elif name == "quit":
                    engine.quit_requested = True; msg = "cerrando"
                else:
                    msg = engine.action(body.get("input"), name)
                self._json({"ok": True, "message": msg})
            else:
                self.send_error(404)

        def _mjpeg(self, iid):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = -1
            try:
                while True:
                    r = engine.inputs.get(iid)
                    if r is not None:
                        r.preview_wanted_until = time.perf_counter() + 2.0
                        if r.jpeg is not None and r.jpeg_seq != last:
                            last = r.jpeg_seq
                            jpg = r.jpeg
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                            self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                            self.wfile.write(jpg + b"\r\n")
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    return H


def serve(engine, host: str, port: int, cfg_path=None, persist=True) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(engine, cfg_path, persist))
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    return httpd
