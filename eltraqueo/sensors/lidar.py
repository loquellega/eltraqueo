# SPDX-License-Identifier: GPL-3.0-or-later
"""LiDAR 2D LDROBOT LD19 / LD06 por puerto serie (230400 baud).

Estado: PREPARADO, SIN PROBAR EN SALA. El parser sigue la hoja de datos del
LD19 (paquete de 47 bytes, cabecera 0x54 0x2C, 12 mediciones por paquete).
Produce Frames de tipo "scan" (ángulo rad, distancia m) que el detector
`lidar_clusters` convierte en observaciones "floor" en metros.

Requiere pyserial (opcional): pip install pyserial
"""
from __future__ import annotations

import math
import struct
from typing import Optional

import numpy as np

from ..contracts import Frame, now
from .base import Sensor

HEADER = 0x54
VERLEN = 0x2C
PKT = 47

# CRC8 del LD19 (polinomio 0x4D)
_CRC = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = ((_c << 1) ^ 0x4D) & 0xFF if _c & 0x80 else (_c << 1) & 0xFF
    _CRC.append(_c)


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = _CRC[(c ^ b) & 0xFF]
    return c


def parse_packet(p: bytes):
    """Devuelve lista de (ángulo_rad, distancia_m, intensidad) o None si no vale."""
    if len(p) != PKT or p[0] != HEADER or p[1] != VERLEN:
        return None
    if crc8(p[:-1]) != p[-1]:
        return None
    start = struct.unpack_from("<H", p, 4)[0] / 100.0
    end = struct.unpack_from("<H", p, 42)[0] / 100.0
    span = (end - start) % 360.0
    out = []
    for i in range(12):
        dist, inten = struct.unpack_from("<HB", p, 6 + 3 * i)
        ang = (start + span * i / 11.0) % 360.0
        out.append((math.radians(ang), dist / 1000.0, inten))
    return out, start, end


class LidarSensor(Sensor):
    produces = "scan"

    def open(self):
        lc = self.all_cfg["detectors"]["lidar"]
        port = self.cfg.get("port") or lc.get("port")
        if not port:
            raise RuntimeError("LiDAR: falta el puerto serie (p. ej. COM5 o /dev/tty.usbserial-…)")
        try:
            import serial  # pyserial
        except ImportError as e:
            raise RuntimeError("LiDAR: falta pyserial (pip install pyserial)") from e
        self.ser = serial.Serial(port, int(lc.get("baud", 230400)), timeout=0.05)
        self.buf = bytearray()
        self.points: list[tuple] = []
        self.last_start = None
        self.info = f"LD19 en {port}"

    def read(self) -> Optional[Frame]:
        self.buf += self.ser.read(512)
        frame = None
        while True:
            i = self.buf.find(bytes([HEADER, VERLEN]))
            if i < 0 or len(self.buf) - i < PKT:
                if i > 0:
                    del self.buf[:i]
                break
            pkt = bytes(self.buf[i:i + PKT])
            del self.buf[:i + PKT]
            res = parse_packet(pkt)
            if not res:
                continue
            pts, start, _ = res
            # Vuelta completa: cuando el ángulo de inicio retrocede
            if self.last_start is not None and start < self.last_start and self.points:
                arr = np.array([(a, d) for a, d, q in self.points if d > 0], np.float32)
                frame = Frame(self.id, now(), "scan", scan=arr)
                self.points = []
            self.last_start = start
            self.points.extend(pts)
        return frame

    def close(self):
        if getattr(self, "ser", None):
            self.ser.close()
