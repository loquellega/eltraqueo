# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from ..contracts import Frame, Observation


class Detector:
    """Contrato de la capa 2.

    process(frame, roi) -> list[Observation]
    draw(img, obs)      -> dibuja la detección sobre la vista previa
    action(name)        -> acciones de la interfaz (p. ej. "capturar fondo")
    """

    name = "base"
    accepts = "image"

    def __init__(self, all_cfg: dict):
        self.all_cfg = all_cfg
        self.status = ""

    @property
    def cfg(self) -> dict:
        return self.all_cfg["detectors"].get(self.name, {})

    def process(self, frame: Frame, roi=(0, 0, 1, 1)) -> list[Observation]:
        raise NotImplementedError

    def draw(self, img, obs: list[Observation]) -> None:
        pass

    def action(self, name: str) -> str:
        return ""


def in_roi(u: float, v: float, roi) -> bool:
    return roi[0] <= u <= roi[2] and roi[1] <= v <= roi[3]
