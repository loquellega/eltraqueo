# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 3 — de observaciones a candidatas en metros.

single_view : una cámara + homografía de piso (v0.1, lista)
floor       : sensores que ya dan metros (LiDAR, UWB)
triangulate : 2+ cámaras calibradas con ChArUco -> x, y, z (fase 2, ver triangulate.py)
"""
from __future__ import annotations

from ..contracts import Candidate, Observation
from ..space import FloorMap

SRC = {"camera": 1, "video": 1, "synthetic": 1, "uwb": 2, "lidar": 4}


def to_candidates(obs: list[Observation], floor: FloorMap, sensor_type: str) -> list[Candidate]:
    src = SRC.get(sensor_type, 1)
    out = []
    for o in obs:
        if o.kind == "floor":
            x, y = o.x, o.y
            q = o.w
        elif o.kind == "point2d":
            x, y = floor.to_floor(o.u, o.v)
            # Una sola vista: sin z y calidad máxima 0.4 si no está calibrada,
            # 0.7 si hay homografía (ver §4 de la especificación).
            q = o.w * (0.7 if floor.calibrated else 0.4)
        else:
            continue
        out.append(Candidate(t=o.t, src=src, x=x, y=y, q=float(min(1.0, q)), tag=o.tag, obs=o))
    return out
