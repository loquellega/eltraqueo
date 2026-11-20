# SPDX-License-Identifier: GPL-3.0-or-later
"""Contratos entre capas (ver tracking-arquitectura-osc.md).

Capa 1 Sensor    -> Frame        (imagen o barrido crudo con marca de tiempo)
Capa 2 Detector  -> Observation  (punto 2D en la imagen, o punto en el piso si el sensor ya es métrico)
Capa 3 Localizer -> Candidate    (posición en metros en el sistema del escenario)
Capa 4 Tracker   -> Target       (ID estable, suavizado, velocidad)
Capa 5 Salida    -> OSC

Cualquier sensor nuevo (LiDAR, UWB, LED IR) solo implementa capas 1 y 2:
el resto no cambia.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


def now() -> float:
    """Reloj único de la computadora central, en segundos."""
    return time.perf_counter()


@dataclass
class Frame:
    sensor: str                 # id del sensor, p. ej. "cam1", "lidar1"
    t: float
    kind: str = "image"         # "image" | "scan"
    image: Optional[np.ndarray] = None      # BGR para cámaras
    scan: Optional[np.ndarray] = None       # N×2 (ángulo rad, distancia m) para LiDAR
    meta: dict = field(default_factory=dict)


@dataclass
class Observation:
    t: float
    sensor: str
    # "point2d"  -> u, v normalizados 0–1 en la imagen del sensor
    # "floor"    -> x, y ya en metros (LiDAR, UWB)
    # "range"    -> distancia tag–anchor (UWB, reservado)
    kind: str
    u: float = 0.0
    v: float = 0.0
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0              # peso / confianza 0–1
    tag: Optional[int] = None   # identidad física (LED IR, UWB) 1–99
    what: str = "blob"          # "blob" | "body" | "led" | "lidar"
    bbox: Optional[tuple] = None          # (u0, v0, u1, v1) normalizado
    area: float = 0.0                      # fracción de la imagen
    keypoints: Optional[np.ndarray] = None # 17×3 (u, v, conf) normalizado
    extra: dict = field(default_factory=dict)


@dataclass
class Candidate:
    t: float
    src: int                    # 1 cámara, 2 UWB, 3 fusión, 4 LiDAR
    x: float
    y: float
    z: Optional[float] = None
    q: float = 1.0
    tag: Optional[int] = None
    obs: Optional[Observation] = None


@dataclass
class Target:
    id: int
    x: float
    y: float
    z: Optional[float] = None
    vx: float = 0.0
    vy: float = 0.0
    q: float = 0.0
    src: int = 1
    tag: Optional[int] = None
    valid: bool = True
    confirmed: bool = False
    hits: int = 0
    last_seen: float = 0.0
    born: float = 0.0
    obs: Optional[Observation] = None
    announced_enter: bool = False

    def as_dict(self, space) -> dict[str, Any]:
        u, v = space.normalize(self.x, self.y)
        d = {
            "id": self.id, "x": round(self.x, 3), "y": round(self.y, 3),
            "u": round(u, 4), "v": round(v, 4),
            "vx": round(self.vx, 3), "vy": round(self.vy, 3),
            "q": round(self.q, 2), "src": self.src, "valid": self.valid,
            "what": self.obs.what if self.obs else None,
        }
        return d
