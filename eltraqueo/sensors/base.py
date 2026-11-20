# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Optional

from ..contracts import Frame


class Sensor:
    """Contrato de la capa 1.

    open()  -> abre el dispositivo (lanza excepción con mensaje legible si falla)
    read()  -> Frame o None si no hay dato nuevo todavía
    close() -> libera el dispositivo
    produces -> "image" (pasa por un detector de imagen) o "floor" (ya da metros)
    """

    produces = "image"

    def __init__(self, input_id: str, cfg: dict, all_cfg: dict):
        self.id = input_id
        self.cfg = cfg
        self.all_cfg = all_cfg
        self.info = ""

    def open(self) -> None:
        raise NotImplementedError

    def read(self) -> Optional[Frame]:
        raise NotImplementedError

    def close(self) -> None:
        pass
