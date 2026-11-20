# SPDX-License-Identifier: GPL-3.0-or-later
"""Archivo de video en bucle: para ensayar sin cámara o repetir una toma."""
from __future__ import annotations

import time
from typing import Optional

import cv2

from ..contracts import Frame, now
from .base import Sensor
from .camera import apply_orientation


class VideoSensor(Sensor):
    def open(self):
        path = self.cfg.get("path", "")
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"no abre el video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self._next = time.perf_counter()
        self.info = f"{int(self.cap.get(3))}×{int(self.cap.get(4))} @ {self.fps:.0f}"

    def read(self) -> Optional[Frame]:
        # Respeta la velocidad real del video
        delay = self._next - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        self._next = max(self._next + 1.0 / self.fps, time.perf_counter() - 0.5)
        ok, img = self.cap.read()
        if not ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = self.cap.read()
            if not ok:
                return None
        return Frame(self.id, now(), "image", image=apply_orientation(img, self.cfg))

    def close(self):
        if getattr(self, "cap", None) is not None:
            self.cap.release()
