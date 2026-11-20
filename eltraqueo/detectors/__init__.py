# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 2 — detectores. Convierten un Frame en Observaciones."""
from .base import Detector
from .blobs import BlobDetector
from .pose import PoseDetector
from .leds import LedDetector
from .lidar_clusters import LidarClusterDetector

REGISTRY = {
    "blobs": BlobDetector,      # manchas / centros de masa (ideal cenital)
    "pose": PoseDetector,       # cuerpos con esqueleto (frontal o lateral)
    "leds": LedDetector,        # LED IR, base para identidad física
    "lidar": LidarClusterDetector,
}

LABELS = {
    "blobs": "manchas",
    "pose": "cuerpos (pose)",
    "leds": "LED IR",
    "lidar": "LiDAR",
}


def make(det_type: str, all_cfg: dict) -> Detector:
    if det_type not in REGISTRY:
        raise ValueError(f"detector desconocido: {det_type}")
    return REGISTRY[det_type](all_cfg)
