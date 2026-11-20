# SPDX-License-Identifier: GPL-3.0-or-later
"""Cuerpos con esqueleto (17 puntos COCO) usando rtmlib (RTMO / RTMPose, ONNX).

Funciona mejor de frente o de lado. Desde el techo usa manchas.
La primera vez descarga el modelo (necesita internet); queda en caché.
"""
from __future__ import annotations

import threading

import cv2
import numpy as np

from ..contracts import Frame, Observation
from .base import Detector, in_roi

JOINTS = ["nose", "eye_l", "eye_r", "ear_l", "ear_r", "shoulder_l", "shoulder_r",
          "elbow_l", "elbow_r", "wrist_l", "wrist_r", "hip_l", "hip_r",
          "knee_l", "knee_r", "ankle_l", "ankle_r"]
BONES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
         (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]


class PoseDetector(Detector):
    name = "pose"

    def __init__(self, all_cfg):
        super().__init__(all_cfg)
        self.model = None
        self._key = None
        self._loading = False
        self._lock = threading.Lock()
        self.error = ""
        self._failed_at = -1e9

    def _ensure_model(self):
        c = self.cfg
        key = (c.get("model"), c.get("mode"), c.get("device"))
        if self.model is not None and key == self._key:
            return True
        if self._loading:
            return False
        import time
        if time.monotonic() - self._failed_at < 15:   # reintento cada 15 s
            return False
        self._loading = True
        self.status = "cargando modelo…"

        def load():
            try:
                from rtmlib import Body
                kw = dict(mode=c.get("mode", "lightweight"), backend="onnxruntime",
                          device=c.get("device", "cpu"))
                if c.get("model", "rtmo") == "rtmo":
                    kw["pose"] = "rtmo"
                m = Body(**kw)
                with self._lock:
                    self.model, self._key = m, key
                self.status, self.error = f"{key[0]} · {key[1]} · {key[2]}", ""
            except Exception as e:  # sin internet la 1ª vez, sin GPU, etc.
                self.error = f"pose no disponible: {e}"
                self.status = self.error
                import time
                self._failed_at = time.monotonic()
            finally:
                self._loading = False

        threading.Thread(target=load, daemon=True).start()
        return False

    def process(self, frame: Frame, roi=(0, 0, 1, 1)):
        if not self._ensure_model():
            return []
        img = frame.image
        H, W = img.shape[:2]
        with self._lock:
            kps, scores = self.model(img)
        if kps is None or len(kps) == 0:
            return []
        c = self.cfg
        smin = float(c.get("min_score", 0.3))
        anchor = c.get("anchor", "hips")
        out = []
        for k, s in zip(np.asarray(kps), np.asarray(scores)):
            good = s >= smin
            if good.sum() < 4:
                continue
            ku, kv = k[:, 0] / W, k[:, 1] / H
            pts = np.stack([ku, kv, s], axis=1).astype(np.float32)
            u, v = _anchor(pts, good, anchor)
            if not in_roi(u, v, roi):
                continue
            gu, gv = ku[good], kv[good]
            out.append(Observation(
                t=frame.t, sensor=frame.sensor, kind="point2d", u=float(u), v=float(v),
                w=float(s[good].mean()), what="body", keypoints=pts,
                bbox=(float(gu.min()), float(gv.min()), float(gu.max()), float(gv.max())),
                area=float((gu.max() - gu.min()) * (gv.max() - gv.min()))))
        out.sort(key=lambda o: -o.w)
        return out[: int(c.get("max_people", 8))]

    def draw(self, img, obs):
        h, w = img.shape[:2]
        for o in obs:
            if o.keypoints is None:
                continue
            k = o.keypoints
            smin = float(self.cfg.get("min_score", 0.3))
            for a, b in BONES:
                if k[a, 2] >= smin and k[b, 2] >= smin:
                    cv2.line(img, (int(k[a, 0] * w), int(k[a, 1] * h)),
                             (int(k[b, 0] * w), int(k[b, 1] * h)), (120, 220, 140), 2)
            for p in k:
                if p[2] >= smin:
                    cv2.circle(img, (int(p[0] * w), int(p[1] * h)), 3, (235, 235, 235), -1)


def _anchor(pts, good, anchor):
    def mean(ids):
        ids = [i for i in ids if good[i]]
        if not ids:
            return None
        return float(pts[ids, 0].mean()), float(pts[ids, 1].mean())

    if anchor == "feet":
        p = mean([15, 16]) or mean([13, 14]) or mean([11, 12])
    elif anchor == "hips":
        p = mean([11, 12]) or mean([5, 6])
    else:
        p = None
    if p is None:
        p = float(pts[good, 0].mean()), float(pts[good, 1].mean())
    return p
