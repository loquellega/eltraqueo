# SPDX-License-Identifier: GPL-3.0-or-later
"""Motor: un hilo por entrada (sensor + detector) y un hilo de salida a tasa fija."""
from __future__ import annotations

import copy
import json
import threading
import time
import traceback

import cv2
import numpy as np

from . import detectors, sensors
from .contracts import now
from .localizers import to_candidates
from .osc_out import OscOut
from .space import FloorMap, Space
from .tracker import Tracker


class InputRunner:
    def __init__(self, engine: "Engine", icfg: dict):
        self.engine = engine
        self.icfg = icfg
        self.id = icfg["id"]
        self.sensor = None
        self.detector = None
        self.floor = FloorMap(engine.space, icfg.get("floor"))
        self.thread = None
        self.running = False
        self.error = ""
        self.fps = 0.0
        self.det_ms = 0.0
        self.latest = None          # (t, [Candidate])
        self.latest_obs = []
        self.seq = 0
        self.jpeg = None
        self.jpeg_seq = 0
        self._last_preview = 0.0
        self.preview_wanted_until = 0.0
        self.lock = threading.Lock()

    @property
    def key(self) -> str:
        """Cambia si hay que reabrir el sensor o cambiar de detector."""
        return json.dumps([self.icfg.get("sensor"), self.icfg.get("detector", {}).get("type")],
                          sort_keys=True)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, name=f"in-{self.id}", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.sensor:
            try:
                self.sensor.close()
            except Exception:
                pass

    def _run(self):
        acfg = self.engine.cfg
        try:
            self.sensor = sensors.make(self.id, self.icfg["sensor"], acfg)
            dtype = self.icfg.get("detector", {}).get("type", "blobs")
            if self.sensor.produces == "scan":
                dtype = "lidar"
            self.detector = detectors.make(dtype, acfg)
            self.sensor.open()
            self.error = ""
        except Exception as e:
            self.error = str(e)
            self.running = False
            return

        stype = self.icfg["sensor"].get("type", "camera")
        frames, t_fps = 0, time.perf_counter()
        while self.running:
            try:
                fr = self.sensor.read()
                if fr is None:
                    time.sleep(0.005)
                    continue
                roi = tuple(self.icfg.get("roi") or (0, 0, 1, 1))
                t0 = time.perf_counter()
                obs = self.detector.process(fr, roi)
                self.det_ms = 0.8 * self.det_ms + 0.2 * (time.perf_counter() - t0) * 1000
                cands = to_candidates(obs, self.floor, stype)
                with self.lock:
                    self.latest = (fr.t, cands)
                    self.latest_obs = obs
                    self.seq += 1
                frames += 1
                el = time.perf_counter() - t_fps
                if el >= 1.0:
                    self.fps, frames, t_fps = frames / el, 0, time.perf_counter()
                self._maybe_preview(fr, obs)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                time.sleep(0.5)

    # --- vista previa -----------------------------------------------------
    def _maybe_preview(self, fr, obs):
        t = time.perf_counter()
        ui = self.engine.cfg["ui"]
        if t > self.preview_wanted_until:
            return
        if t - self._last_preview < 1.0 / max(1, ui.get("preview_fps", 12)):
            return
        self._last_preview = t
        if fr.kind == "scan":
            img = self.detector.render(self.engine.space)
        else:
            src = fr.image
            pw = int(ui.get("preview_width", 640))
            h, w = src.shape[:2]
            img = cv2.resize(src, (pw, int(h * pw / w)), interpolation=cv2.INTER_AREA)
            self.detector.draw(img, obs)
            self._draw_overlay(img)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            self.jpeg = buf.tobytes()
            self.jpeg_seq += 1

    def _draw_overlay(self, img):
        h, w = img.shape[:2]
        roi = self.icfg.get("roi") or [0, 0, 1, 1]
        if list(roi) != [0, 0, 1, 1]:
            cv2.rectangle(img, (int(roi[0] * w), int(roi[1] * h)),
                          (int(roi[2] * w), int(roi[3] * h)), (90, 90, 90), 1)
        pts = (self.icfg.get("floor") or {}).get("image") or []
        for i, (u, v) in enumerate(pts):
            p = (int(u * w), int(v * h))
            cv2.drawMarker(img, p, (17, 196, 118), cv2.MARKER_CROSS, 12, 1)
            cv2.putText(img, str(i + 1), (p[0] + 6, p[1] - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, (17, 196, 118), 1, cv2.LINE_AA)
        if len(pts) >= 4:
            cv2.polylines(img, [np.int32([[u * w, v * h] for u, v in pts[:4]])], True,
                          (60, 110, 40), 1)
        for tg in self.engine.snapshot_targets():
            o = tg.obs
            if o is None or o.sensor != self.id or o.kind != "point2d":
                continue
            p = (int(o.u * w), int(o.v * h))
            col = (17, 196, 118) if tg.valid else (120, 120, 120)
            cv2.circle(img, p, 5, col, -1)
            cv2.putText(img, str(tg.id), (p[0] + 10, p[1] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 255, 255), 1, cv2.LINE_AA)


class Engine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.space = Space(cfg["space"])
        self.tracker = Tracker(cfg["tracker"])
        self.osc = OscOut(cfg["osc"])
        self.inputs: dict[str, InputRunner] = {}
        self.running = False
        self._out_thread = None
        self._targets_snapshot = []
        self._lock = threading.RLock()
        self._consumed: dict[str, int] = {}
        self.out_hz = 0.0
        self.quit_requested = False

    # --- ciclo de vida ------------------------------------------------------
    def start(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            for icfg in self.cfg["inputs"]:
                if icfg.get("enabled", True):
                    self._start_input(icfg)
            self._out_thread = threading.Thread(target=self._out_loop, name="osc", daemon=True)
            self._out_thread.start()

    def stop(self):
        with self._lock:
            self.running = False
            for r in list(self.inputs.values()):
                r.stop()
            self.inputs.clear()
            self.tracker.reset()
        if self._out_thread:
            self._out_thread.join(timeout=2)
        self.osc.send_frame(now(), [], self.tracker.pop_events(), self.space)
        self.osc.send_status(0.0, 0)

    def _start_input(self, icfg):
        r = InputRunner(self, icfg)
        self.inputs[r.id] = r
        r.start()

    def apply_config(self, new_cfg: dict):
        """Aplica cambios en caliente; solo reabre las entradas que cambiaron."""
        with self._lock:
            old_inputs = {i["id"]: i for i in self.cfg["inputs"]}
            # Mutar en sitio: detectores y tracker leen self.cfg en vivo.
            for k in list(self.cfg.keys()):
                if k not in new_cfg:
                    del self.cfg[k]
            for k, v in new_cfg.items():
                if k in ("detectors", "tracker", "osc", "ui", "space") and isinstance(self.cfg.get(k), dict):
                    self.cfg[k].clear()
                    self.cfg[k].update(copy.deepcopy(v))
                else:
                    self.cfg[k] = copy.deepcopy(v)
            self.space.update(self.cfg["space"])
            self.tracker.cfg = self.cfg["tracker"]
            self.osc.cfg = self.cfg["osc"]
            if not self.running:
                return
            new_ids = {i["id"] for i in self.cfg["inputs"] if i.get("enabled", True)}
            for iid in list(self.inputs):
                if iid not in new_ids:
                    self.inputs.pop(iid).stop()
            for icfg in self.cfg["inputs"]:
                if not icfg.get("enabled", True):
                    continue
                r = self.inputs.get(icfg["id"])
                if r is None:
                    self._start_input(icfg)
                    continue
                old = old_inputs.get(icfg["id"], {})
                same = json.dumps([old.get("sensor"), old.get("detector", {}).get("type")],
                                  sort_keys=True) == json.dumps(
                    [icfg.get("sensor"), icfg.get("detector", {}).get("type")], sort_keys=True)
                if same and r.running:
                    r.icfg = icfg
                    r.floor.set(icfg.get("floor") or {})
                else:
                    self.inputs.pop(icfg["id"]).stop()
                    self._start_input(icfg)

    def action(self, input_id: str | None, name: str) -> str:
        if name == "reset_ids":
            self.tracker.reset()
            return "IDs reiniciados"
        r = self.inputs.get(input_id or "")
        if r and r.detector:
            return r.detector.action(name) or ""
        return ""

    # --- salida -------------------------------------------------------------
    def _out_loop(self):
        last_status = 0.0
        ticks, t_hz = 0, time.perf_counter()
        while self.running:
            rate = max(1, int(self.cfg["osc"].get("rate", 30)))
            t0 = time.perf_counter()
            cands, fresh = [], False
            for iid, r in list(self.inputs.items()):
                with r.lock:
                    if r.latest is not None and r.seq != self._consumed.get(iid):
                        self._consumed[iid] = r.seq
                        cands.extend(r.latest[1])
                        fresh = True
            t = now()
            self.tracker.update(cands if fresh else None, t)
            pub = self.tracker.published()
            with self._lock:
                self._targets_snapshot = pub
            try:
                self.osc.send_frame(t, pub, self.tracker.pop_events(), self.space)
                if t0 - last_status >= 1.0:
                    hz = max((r.fps for r in self.inputs.values()), default=0.0)
                    self.osc.send_status(hz, 2)
                    last_status = t0
            except Exception as e:
                self.osc.error = str(e)
            ticks += 1
            el = time.perf_counter() - t_hz
            if el >= 1.0:
                self.out_hz, ticks, t_hz = ticks / el, 0, time.perf_counter()
            dt = 1.0 / rate - (time.perf_counter() - t0)
            if dt > 0:
                time.sleep(dt)

    def snapshot_targets(self):
        with self._lock:
            return list(self._targets_snapshot)

    def state(self) -> dict:
        ins = []
        for icfg in self.cfg["inputs"]:
            r = self.inputs.get(icfg["id"])
            d = {"id": icfg["id"], "enabled": icfg.get("enabled", True),
                 "running": bool(r and r.running), "fps": round(r.fps, 1) if r else 0,
                 "det_ms": round(r.det_ms, 1) if r else 0,
                 "error": r.error if r else "", "info": (r.sensor.info if r and r.sensor else ""),
                 "status": (r.detector.status if r and r.detector else ""),
                 "detections": len(r.latest_obs) if r else 0,
                 "calibrated": bool(r and r.floor.calibrated)}
            ins.append(d)
        return {
            "running": self.running,
            "inputs": ins,
            "targets": [t.as_dict(self.space) for t in self.snapshot_targets()],
            "osc": {"sent": self.osc.sent, "hz": round(self.out_hz, 1), "error": self.osc.error,
                    "seq": self.osc.seq},
        }
