# SPDX-License-Identifier: GPL-3.0-or-later
"""Fase 2 — triangulación entre 2+ cámaras (x, y, z).

Plan (no activo en v0.1):
1. Intrínsecas por cámara con tablero de ajedrez -> calib/camN.json (K, dist).
2. Extrínsecas con un ChArUco sobre el origen del escenario -> R, t por cámara.
3. Por cada par de observaciones (misma persona en dos vistas, asociadas por
   geometría epipolar), cv2.triangulatePoints con las matrices P = K [R|t].
4. Las webcams no están sincronizadas: interpolar cada observación a un
   tiempo común usando Observation.t antes de triangular.
5. Calidad: número de vistas + error de reproyección.

La función ya existe para pruebas con datos calibrados.
"""
from __future__ import annotations

import cv2
import numpy as np


def triangulate_pair(P1: np.ndarray, P2: np.ndarray, p1, p2) -> np.ndarray:
    """P1, P2: matrices 3×4. p1, p2: puntos en píxeles sin distorsión (x, y)."""
    X = cv2.triangulatePoints(P1, P2, np.float64(p1).reshape(2, 1), np.float64(p2).reshape(2, 1))
    return (X[:3] / X[3]).ravel()
