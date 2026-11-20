# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from typing import Optional

import cv2

from ..contracts import Frame, now
from .base import Sensor


def _default_backend() -> int:
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    if sys.platform.startswith("win"):
        return cv2.CAP_DSHOW   # abre rápido y respeta resolución en la mayoría de webcams
    return cv2.CAP_V4L2


def list_cameras(max_probe: int = 6) -> list[dict]:
    """Cámaras disponibles con nombre cuando el sistema lo da."""
    out: list[dict] = []
    try:
        from cv2_enumerate_cameras import enumerate_cameras  # nombres reales
        backend = _default_backend()
        for c in enumerate_cameras(backend):
            out.append({"index": int(c.index), "backend": int(c.backend),
                        "name": c.name or f"Cámara {c.index}"})
        if out:
            return out
    except Exception:
        pass
    # Respaldo: probar índices
    backend = _default_backend()
    for i in range(max_probe):
        cap = cv2.VideoCapture(i, backend)
        ok = cap.isOpened()
        cap.release()
        if ok:
            out.append({"index": i, "backend": int(backend), "name": f"Cámara {i}"})
    return out


class CameraSensor(Sensor):
    def open(self):
        idx = int(self.cfg.get("index", 0))
        backend = int(self.cfg.get("backend") or 0) or _default_backend()
        self.cap = cv2.VideoCapture(idx, backend)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(idx)  # último intento con lo que elija OpenCV
        if not self.cap.isOpened():
            msg = f"no abre la cámara {idx}"
            if sys.platform == "darwin":
                msg += " (revisa Ajustes del Sistema → Privacidad → Cámara)"
            raise RuntimeError(msg)
        w, h, fps = self.cfg.get("width"), self.cfg.get("height"), self.cfg.get("fps")
        if w: self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
        if h: self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
        if fps: self.cap.set(cv2.CAP_PROP_FPS, int(fps))
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # menos latencia
        except Exception:
            pass
        rw = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        rh = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.info = f"{rw}×{rh}"

    def read(self) -> Optional[Frame]:
        ok, img = self.cap.read()
        if not ok or img is None:
            return None
        img = apply_orientation(img, self.cfg)
        return Frame(self.id, now(), "image", image=img)

    def close(self):
        if getattr(self, "cap", None) is not None:
            self.cap.release()
            self.cap = None


def apply_orientation(img, cfg: dict):
    flip = cfg.get("flip", "none")
    if flip == "h":
        img = cv2.flip(img, 1)
    elif flip == "v":
        img = cv2.flip(img, 0)
    elif flip == "hv":
        img = cv2.flip(img, -1)
    rot = int(cfg.get("rotate", 0)) % 360
    if rot == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    elif rot == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img
