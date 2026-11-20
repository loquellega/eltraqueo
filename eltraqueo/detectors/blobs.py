# SPDX-License-Identifier: GPL-3.0-or-later
"""Manchas: resta de fondo + contornos. Lo más barato y estable desde el techo.

Métodos:
  background  fondo capturado con un botón (escena vacía). El más estable en teatro.
  mog2        fondo que se aprende solo; se "come" a quien se queda quieto.
  bright      umbral de brillo directo (cuerpos iluminados sobre piso negro, o cámara IR).
"""
from __future__ import annotations

import cv2
import numpy as np

from ..contracts import Frame, Observation
from .base import Detector, in_roi

WORK_W = 480  # se procesa a esta anchura: rápido y suficiente para centros


class BlobDetector(Detector):
    name = "blobs"

    def __init__(self, all_cfg):
        super().__init__(all_cfg)
        self.bg = None
        self.mog = None
        self._grab_bg = True   # captura el primer cuadro como fondo
        self.mask = None

    def action(self, name: str) -> str:
        if name == "capture_background":
            self._grab_bg = True
            return "fondo capturado"
        return ""

    def _prep(self, img):
        h, w = img.shape[:2]
        s = WORK_W / float(w)
        small = cv2.resize(img, (WORK_W, int(h * s)), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        k = int(self.cfg.get("blur", 5)) | 1
        if k > 1:
            g = cv2.GaussianBlur(g, (k, k), 0)
        return g

    def process(self, frame: Frame, roi=(0, 0, 1, 1)):
        c = self.cfg
        g = self._prep(frame.image)
        method = c.get("method", "background")
        thr = int(c.get("threshold", 32))

        if method == "bright":
            _, mask = cv2.threshold(g, thr, 255, cv2.THRESH_BINARY)
        elif method == "mog2":
            if self.mog is None:
                self.mog = cv2.createBackgroundSubtractorMOG2(500, 16, False)
            mask = self.mog.apply(g, learningRate=-1)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        else:
            if self._grab_bg or self.bg is None or self.bg.shape != g.shape:
                self.bg = g.astype(np.float32)
                self._grab_bg = False
                self.status = "fondo capturado"
            diff = cv2.absdiff(g, cv2.convertScaleAbs(self.bg))
            _, mask = cv2.threshold(diff, thr, 255, cv2.THRESH_BINARY)
            lr = float(c.get("learn_rate", 0.0))
            if lr > 0:
                cv2.accumulateWeighted(g, self.bg, lr, mask=cv2.bitwise_not(mask))

        d = int(c.get("dilate", 2))
        if d > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
            mask = cv2.dilate(mask, k, iterations=d)
        self.mask = mask

        H, W = mask.shape
        total = float(H * W)
        amin, amax = float(c.get("min_area", 0.002)), float(c.get("max_area", 0.25))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for cnt in contours:
            a = cv2.contourArea(cnt) / total
            if a < amin or a > amax:
                continue
            m = cv2.moments(cnt)
            if m["m00"] <= 0:
                continue
            u, v = m["m10"] / m["m00"] / W, m["m01"] / m["m00"] / H
            if not in_roi(u, v, roi):
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            out.append(Observation(
                t=frame.t, sensor=frame.sensor, kind="point2d", u=u, v=v,
                w=min(1.0, a / max(amin * 4, 1e-6)), what="blob", area=a,
                bbox=(x / W, y / H, (x + bw) / W, (y + bh) / H)))
        out.sort(key=lambda o: -o.area)
        return out[: int(c.get("max_blobs", 12))]

    def draw(self, img, obs):
        h, w = img.shape[:2]
        if self.mask is not None:
            m = cv2.resize(self.mask, (w, h), interpolation=cv2.INTER_NEAREST)
            tint = np.zeros_like(img)
            tint[m > 0] = (40, 120, 60)
            cv2.addWeighted(img, 1.0, tint, 0.45, 0, dst=img)
        for o in obs:
            if o.bbox:
                x0, y0, x1, y1 = o.bbox
                cv2.rectangle(img, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)),
                              (200, 200, 200), 1)
