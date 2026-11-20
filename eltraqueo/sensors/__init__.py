# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 1 — sensores. Para sumar uno nuevo: subclase de Sensor + entrada en REGISTRY."""
from .base import Sensor
from .camera import CameraSensor, list_cameras
from .video import VideoSensor
from .synthetic import SyntheticSensor
from .lidar import LidarSensor

REGISTRY = {
    "camera": CameraSensor,
    "video": VideoSensor,
    "synthetic": SyntheticSensor,
    "lidar": LidarSensor,
}


def make(input_id: str, cfg: dict, all_cfg: dict) -> Sensor:
    kind = cfg.get("type", "camera")
    if kind not in REGISTRY:
        raise ValueError(f"sensor desconocido: {kind}")
    return REGISTRY[kind](input_id, cfg, all_cfg)


__all__ = ["Sensor", "REGISTRY", "make", "list_cameras"]
