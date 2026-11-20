# SPDX-License-Identifier: GPL-3.0-or-later
"""LED IR — base para la vía de identidad física.

v0.1: detecta puntos muy brillantes (cámara con filtro IR o exposición baja).
Gancho preparado: si `decode_blink` está activo, cada punto se sigue cuadro a
cuadro y su secuencia encendido/apagado se compara con `codes` para asignar
un tag 1–99. La asignación definitiva de tags (y su sincronía con el LED)
se afina cuando tengamos el hardware.
"""
from __future__ import annotations

from collections import deque

import cv2

from ..contracts import Frame, Observation
from .base import Detector, in_roi


class LedDetector(Detector):
    name = "leds"

    def __init__(self, all_cfg):
        super().__init__(all_cfg)
        self.tracks: list[dict] = []   # {u, v, bits: deque, last}

    def process(self, frame: Frame, roi=(0, 0, 1, 1)):
        c = self.cfg
        g = cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY)
        H, W = g.shape
        _, mask = cv2.threshold(g, int(c.get("threshold", 230)), 255, cv2.THRESH_BINARY)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        amin, amax = float(c.get("min_area", 2e-5)), float(c.get("max_area", 2e-3))
        spots = []
        for cnt in cnts:
            a = max(cv2.contourArea(cnt), 1.0) / (H * W)
            if a < amin or a > amax:
                continue
            m = cv2.moments(cnt)
            if m["m00"] <= 0:
                (x, y), _ = cv2.minEnclosingCircle(cnt)
                u, v = x / W, y / H
            else:
                u, v = m["m10"] / m["m00"] / W, m["m01"] / m["m00"] / H
            if in_roi(u, v, roi):
                spots.append((u, v, a))

        if c.get("decode_blink"):
            self._update_blink(spots, frame.t)

        out = []
        for u, v, a in spots:
            out.append(Observation(t=frame.t, sensor=frame.sensor, kind="point2d",
                                   u=u, v=v, w=1.0, what="led", area=a,
                                   tag=self._tag_near(u, v)))
        return out

    # --- gancho de identidad por parpadeo ---------------------------------
    def _update_blink(self, spots, t):
        seen = set()
        for tr in self.tracks:
            best, bd = None, 0.03
            for i, (u, v, _) in enumerate(spots):
                d = abs(u - tr["u"]) + abs(v - tr["v"])
                if d < bd and i not in seen:
                    best, bd = i, d
            if best is not None:
                seen.add(best)
                tr["u"], tr["v"] = spots[best][:2]
                tr["bits"].append("1")
                tr["last"] = t
            else:
                tr["bits"].append("0")
        for i, (u, v, _) in enumerate(spots):
            if i not in seen:
                self.tracks.append({"u": u, "v": v, "bits": deque("1", maxlen=16),
                                    "last": t, "tag": None})
        self.tracks = [tr for tr in self.tracks if t - tr["last"] < 1.0]
        codes = self.cfg.get("codes", {}) or {}
        for tr in self.tracks:
            s = "".join(tr["bits"])
            for tag, code in codes.items():
                if code and len(s) >= 2 * len(code) and code * 2 in s:
                    tr["tag"] = int(tag)

    def _tag_near(self, u, v):
        for tr in self.tracks:
            if tr.get("tag") and abs(u - tr["u"]) + abs(v - tr["v"]) < 0.03:
                return tr["tag"]
        return None

    def draw(self, img, obs):
        h, w = img.shape[:2]
        for o in obs:
            p = (int(o.u * w), int(o.v * h))
            cv2.circle(img, p, 9, (120, 220, 140), 1)
            if o.tag:
                cv2.putText(img, f"tag {o.tag}", (p[0] + 10, p[1] - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (235, 235, 235), 1, cv2.LINE_AA)
