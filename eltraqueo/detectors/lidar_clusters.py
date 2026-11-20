# SPDX-License-Identifier: GPL-3.0-or-later
"""LiDAR 2D: barrido -> grupos de puntos -> centros en metros (observaciones "floor").

PREPARADO, SIN PROBAR EN SALA. El LiDAR va al nivel de las piernas o la cadera;
cada persona aparece como un arco corto de puntos.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from ..contracts import Frame, Observation
from .base import Detector


class LidarClusterDetector(Detector):
    name = "lidar"
    accepts = "scan"

    def __init__(self, all_cfg):
        super().__init__(all_cfg)
        self.last_xy = np.zeros((0, 2), np.float32)

    def process(self, frame: Frame, roi=(0, 0, 1, 1)):
        c = self.cfg
        scan = frame.scan
        if scan is None or len(scan) == 0:
            return []
        a, d = scan[:, 0], scan[:, 1]
        keep = (d >= c.get("min_range", 0.15)) & (d <= c.get("max_range", 12.0))
        a, d = a[keep], d[keep]
        order = np.argsort(a)
        a, d = a[order], d[order]
        hd = math.radians(float(c.get("heading_deg", 90.0)))
        px, py = c.get("position", [0.0, 0.0])
        # El LD19 gira en sentido horario; se convierte a ejes del escenario.
        th = hd - a
        xs = px + d * np.cos(th)
        ys = py + d * np.sin(th)
        xy = np.stack([xs, ys], 1).astype(np.float32)
        self.last_xy = xy

        gap = float(c.get("cluster_gap", 0.25))
        minp = int(c.get("min_points", 3))
        out, cur = [], [0] if len(xy) else []
        for i in range(1, len(xy)):
            if np.linalg.norm(xy[i] - xy[i - 1]) <= gap:
                cur.append(i)
            else:
                out.append(cur)
                cur = [i]
        if cur:
            out.append(cur)
        # une el último con el primero si el barrido da la vuelta
        if len(out) > 1 and np.linalg.norm(xy[out[0][0]] - xy[out[-1][-1]]) <= gap:
            out[0] = out[-1] + out[0]
            out.pop()

        obs = []
        for idx in out:
            if len(idx) < minp:
                continue
            cx, cy = xy[idx].mean(0)
            obs.append(Observation(t=frame.t, sensor=frame.sensor, kind="floor",
                                   x=float(cx), y=float(cy), w=min(1.0, len(idx) / 12),
                                   what="lidar"))
        return obs

    def render(self, space, size=(480, 480)):
        """Vista superior del barrido para la interfaz."""
        w, h = size
        img = np.full((h, w, 3), 12, np.uint8)
        for x, y in self.last_xy:
            u, v = space.normalize(float(x), float(y))
            cv2.circle(img, (int(u * w), int((1 - v) * h)), 1, (200, 200, 200), -1)
        return img
