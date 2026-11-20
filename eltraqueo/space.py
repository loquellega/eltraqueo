# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 0 (espacio) y capa 3 de una sola vista (imagen -> piso).

Con una cámara, la posición en el piso se obtiene con una homografía:
4 puntos marcados en el piso (en la imagen) y sus coordenadas en metros.
Sin calibrar, la imagen completa se estira a los límites del escenario.
"""
from __future__ import annotations

import cv2
import numpy as np


class Space:
    def __init__(self, cfg: dict):
        self.update(cfg)

    def update(self, cfg: dict):
        lim = cfg["limits"]
        self.xmin, self.xmax = float(lim["xmin"]), float(lim["xmax"])
        self.ymin, self.ymax = float(lim["ymin"]), float(lim["ymax"])
        self.name = cfg.get("name", "")

    def normalize(self, x: float, y: float) -> tuple[float, float]:
        u = (x - self.xmin) / max(1e-9, self.xmax - self.xmin)
        v = (y - self.ymin) / max(1e-9, self.ymax - self.ymin)
        return float(u), float(v)

    def denormalize(self, u: float, v: float) -> tuple[float, float]:
        return (self.xmin + u * (self.xmax - self.xmin),
                self.ymin + v * (self.ymax - self.ymin))


class FloorMap:
    """Imagen (u,v 0–1) -> piso (x,y m) para una entrada."""

    def __init__(self, space: Space, floor_cfg: dict | None):
        self.space = space
        self.H = None
        self.set(floor_cfg or {})

    def set(self, floor_cfg: dict):
        img = floor_cfg.get("image") or []
        wld = floor_cfg.get("world") or []
        self.H = None
        if len(img) >= 4 and len(img) == len(wld):
            H, _ = cv2.findHomography(np.float32(img), np.float32(wld))
            self.H = H

    @property
    def calibrated(self) -> bool:
        return self.H is not None

    def to_floor(self, u: float, v: float) -> tuple[float, float]:
        if self.H is None:
            # Sin calibrar: arriba de la imagen = fondo del escenario.
            return self.space.denormalize(u, 1.0 - v)
        p = np.float32([[[u, v]]])
        q = cv2.perspectiveTransform(p, self.H)[0, 0]
        return float(q[0]), float(q[1])
