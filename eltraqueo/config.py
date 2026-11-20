# SPDX-License-Identifier: GPL-3.0-or-later
"""Configuración persistente en ~/.eltraqueo/config.json."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("ELTRAQUEO_HOME", Path.home() / ".eltraqueo"))
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT = {
    "version": 1,
    # Capa 0: espacio. Metros, origen al centro del proscenio,
    # x+ derecha del público, y+ hacia el fondo.
    "space": {
        "name": "Escenario",
        "limits": {"xmin": -5.0, "xmax": 5.0, "ymin": 0.0, "ymax": 10.0},
    },
    # Entradas: un sensor + un detector cada una.
    "inputs": [
        {
            "id": "cam1",
            "enabled": True,
            "sensor": {"type": "camera", "index": 0, "backend": 0,
                       "width": 1280, "height": 720, "fps": 30,
                       "flip": "none", "rotate": 0},
            "detector": {"type": "blobs"},
            # Calibración de piso: 4 puntos de la imagen (u,v 0–1) y sus
            # equivalentes en metros. Vacío = la imagen completa cubre los límites.
            "floor": {"image": [], "world": []},
            # Rectángulo útil de la imagen (0–1); afuera se ignora.
            "roi": [0.0, 0.0, 1.0, 1.0],
        }
    ],
    "detectors": {
        "blobs": {
            "method": "background",   # "background" (fondo capturado) | "mog2" | "bright"
            "threshold": 32,
            "blur": 5,
            "min_area": 0.002,        # fracción de la imagen
            "max_area": 0.25,
            "dilate": 2,
            "learn_rate": 0.0,        # 0 = fondo fijo; >0 se adapta lento
            "max_blobs": 12,
        },
        "pose": {
            "model": "rtmo",          # "rtmo" (una etapa, mejor con mucha gente) | "rtmpose"
            "mode": "lightweight",    # lightweight | balanced | performance
            "device": "cpu",          # cpu | cuda | mps
            "min_score": 0.3,
            "anchor": "hips",         # punto que se publica como posición: hips | feet | center
            "send_joints": False,
            "max_people": 8,
        },
        "leds": {
            # LED IR: preparado para la vía de identidad. v0.1 detecta puntos
            # brillantes; el decodificador de parpadeo asigna tag 1–99.
            "threshold": 230,
            "min_area": 0.00002,
            "max_area": 0.002,
            "decode_blink": False,
            "codes": {},              # {"1": "1010", "2": "1100"} patrón por tag
        },
        "lidar": {
            # LD19 / LD06 por serie: preparado, sin probar en sala.
            "port": "",
            "baud": 230400,
            "position": [0.0, -0.5],  # metros, dónde está el LiDAR en el escenario
            "heading_deg": 90.0,      # hacia dónde mira el ángulo 0
            "min_range": 0.15,
            "max_range": 12.0,
            "cluster_gap": 0.25,
            "min_points": 3,
        },
    },
    "tracker": {
        "max_targets": 8,
        "match_radius": 0.9,      # metros
        "confirm_hits": 3,
        "smoothing": 0.5,         # 0 = sin suavizado, 0.9 = muy suave
        "invalid_after": 0.25,    # s sin datos -> valid 0
        "grace": 2.0,             # s sin datos -> exit
        "merge_radius": 0.4,      # une candidatas de varias cámaras
    },
    "osc": {
        "enabled": True,
        "rate": 30,
        "destinations": [{"host": "127.0.0.1", "port": 9100}],
        "prefix": "/tracking",
        "bundle": False,
        "send": {
            "frame": True, "position": True, "norm": True, "velocity": True,
            "valid": True, "quality": True, "source": True, "events": True,
            "bbox": False, "area": False, "joints": False, "count": True,
        },
    },
    "ui": {"port": 8765, "open_browser": True, "preview_fps": 12, "preview_width": 640},
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path: Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    if p.exists():
        try:
            return deep_merge(DEFAULT, json.loads(p.read_text("utf-8")))
        except Exception as e:  # archivo dañado: seguimos con lo de fábrica
            print(f"[config] no se pudo leer {p}: {e}")
    return copy.deepcopy(DEFAULT)


def save(cfg: dict, path: Path | None = None) -> Path:
    p = Path(path) if path else CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(p)
    return p
