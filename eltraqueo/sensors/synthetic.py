# SPDX-License-Identifier: GPL-3.0-or-later
"""Escena de prueba: manchas que caminan sobre fondo oscuro, vistas desde arriba,
más un LED que parpadea. Sirve para probar OSC sin cámara."""
from __future__ import annotations

import math
import time
from typing import Optional

import cv2
import numpy as np

from ..contracts import Frame, now
from .base import Sensor


class SyntheticSensor(Sensor):
    def open(self):
        self.w = int(self.cfg.get("width", 640))
        self.h = int(self.cfg.get("height", 360))
        self.n = int(self.cfg.get("people", 3))
        self.fps = float(self.cfg.get("fps", 30))
        self.t0 = time.perf_counter()
        self._next = self.t0
        rng = np.random.default_rng(7)
        self.params = rng.uniform(0.2, 1.0, size=(max(1, self.n), 4))
        self.info = f"sintético {self.w}×{self.h}, {self.n} personas"

    def read(self) -> Optional[Frame]:
        delay = self._next - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        self._next += 1.0 / self.fps
        t = time.perf_counter() - self.t0
        img = np.full((self.h, self.w, 3), 18, np.uint8)
        # textura de piso para que se vea algo
        cv2.rectangle(img, (0, 0), (self.w - 1, self.h - 1), (40, 40, 40), 1)
        # El primer segundo y medio el escenario está vacío (para capturar fondo)
        for i in range(self.n if t > 1.5 else 0):
            a, b, c, d = self.params[i]
            u = 0.5 + 0.38 * math.sin(t * 0.35 * a + i * 2.1)
            v = 0.5 + 0.36 * math.sin(t * 0.27 * b + i * 1.3 + c)
            r = int(self.h * (0.05 + 0.015 * d))
            cv2.circle(img, (int(u * self.w), int(v * self.h)), r, (190, 190, 190), -1)
        # LED parpadeando (patrón 1010 a 10 Hz)
        if int(t * 10) % 2 == 0:
            cv2.circle(img, (int(self.w * 0.9), int(self.h * 0.1)), 3, (255, 255, 255), -1)
        return Frame(self.id, now(), "image", image=img)
