# SPDX-License-Identifier: GPL-3.0-or-later
"""Pruebas rápidas sin cámara: python -m pytest tests  (o python tests/test_core.py)."""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eltraqueo import config
from eltraqueo.contracts import Candidate, Frame, Observation
from eltraqueo.detectors.lidar_clusters import LidarClusterDetector
from eltraqueo.sensors.lidar import HEADER, PKT, VERLEN, crc8, parse_packet
from eltraqueo.space import FloorMap, Space
from eltraqueo.tracker import Tracker


def cand(x, y, tag=None, sensor="cam1"):
    o = Observation(t=0, sensor=sensor, kind="point2d")
    return Candidate(t=0, src=1, x=x, y=y, q=0.8, tag=tag, obs=o)


def test_ids_estables_y_eventos():
    tr = Tracker(dict(config.DEFAULT["tracker"]))
    t = 0.0
    for k in range(10):
        t += 1 / 30
        tr.update([cand(0 + k * 0.02, 2), cand(3, 5 - k * 0.02)], t)
    pub = tr.published()
    assert [p.id for p in pub] == [101, 102]
    ev = tr.pop_events()
    assert ("enter", 101) in ev and ("enter", 102) in ev
    # desaparece uno: primero valid 0, luego exit
    for _ in range(15):
        t += 1 / 30
        tr.update([cand(0.2, 2)], t)
    assert not tr.targets[102].valid
    t += 3
    tr.update([cand(0.2, 2)], t)
    assert ("exit", 102) in tr.pop_events()


def test_tag_adopta_id():
    tr = Tracker(dict(config.DEFAULT["tracker"]))
    t = 0
    for _ in range(5):
        t += 0.03
        tr.update([cand(1, 1)], t)
    assert 101 in tr.targets
    t += 0.03
    tr.update([cand(1.05, 1, tag=7)], t)
    assert 7 in tr.targets and 101 not in tr.targets


def test_fusion_dos_camaras():
    tr = Tracker(dict(config.DEFAULT["tracker"]))
    t = 0
    for _ in range(5):
        t += 0.03
        tr.update([cand(1, 1, sensor="cam1"), cand(1.1, 1.05, sensor="cam2")], t)
    assert len(tr.published()) == 1


def test_homografia():
    sp = Space(config.DEFAULT["space"])
    fm = FloorMap(sp, {"image": [[0, 0], [1, 0], [1, 1], [0, 1]],
                       "world": [[-2, 6], [2, 6], [2, 2], [-2, 2]]})
    x, y = fm.to_floor(0.5, 0.5)
    assert abs(x) < 1e-4 and abs(y - 4) < 1e-4
    sin = FloorMap(sp, {})
    assert sin.to_floor(0, 0) == (-5.0, 10.0)   # arriba-izq = fondo izq.


def _ld19_packet(start_deg, end_deg, dists_mm):
    body = bytes([HEADER, VERLEN]) + struct.pack("<HH", 3600, int(start_deg * 100))
    for d in dists_mm:
        body += struct.pack("<HB", d, 200)
    body += struct.pack("<HH", int(end_deg * 100), 0)
    return body + bytes([crc8(body)])


def test_ld19_parser():
    p = _ld19_packet(10, 21, [1000] * 12)
    assert len(p) == PKT
    pts, s, e = parse_packet(p)
    assert len(pts) == 12 and abs(pts[0][1] - 1.0) < 1e-6
    assert abs(math.degrees(pts[-1][0]) - 21) < 1e-3
    bad = bytearray(p); bad[10] ^= 0xFF
    assert parse_packet(bytes(bad)) is None


def test_lidar_clusters():
    cfg = config.load("/nonexistent.json")
    det = LidarClusterDetector(cfg)
    import numpy as np
    ang = np.radians(np.r_[np.linspace(0, 3, 6), np.linspace(40, 43, 6)])
    dist = np.r_[np.full(6, 2.0), np.full(6, 4.0)]
    obs = det.process(Frame("l", 0, "scan", scan=np.stack([ang, dist], 1).astype(np.float32)))
    assert len(obs) == 2 and all(o.kind == "floor" for o in obs)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
