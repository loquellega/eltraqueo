# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 5 — salida OSC/UDP según la especificación común (/tracking/...).

Solo enteros y flotantes, sin cadenas, para Isadora (OSC Listener) y
TouchDesigner (OSC In CHOP / DAT).
"""
from __future__ import annotations

from pythonosc import osc_bundle_builder, osc_message_builder
from pythonosc.udp_client import UDPClient

from .contracts import Target


def _msg(addr: str, *args):
    b = osc_message_builder.OscMessageBuilder(address=addr)
    for a in args:
        if isinstance(a, bool):
            b.add_arg(int(a), "i")
        elif isinstance(a, int):
            b.add_arg(a, "i")
        else:
            b.add_arg(float(a), "f")
    return b.build()


class OscOut:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.clients: list[UDPClient] = []
        self._dest_key = None
        self.seq = 0
        self.sent = 0
        self.error = ""
        self._refresh()

    def _refresh(self):
        dests = [(d.get("host", "127.0.0.1"), int(d.get("port", 9100)))
                 for d in self.cfg.get("destinations", []) if d.get("host")]
        key = tuple(dests)
        if key == self._dest_key:
            return
        self.clients = []
        self.error = ""
        for h, p in dests:
            try:
                cl = UDPClient(h, p, allow_broadcast=True)
                self.clients.append(cl)
            except Exception as e:
                self.error = f"{h}:{p} — {e}"
        self._dest_key = key

    def _send_all(self, msgs):
        if not msgs:
            return
        if self.cfg.get("bundle"):
            bb = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
            for m in msgs:
                bb.add_content(m)
            packets = [bb.build()]
        else:
            packets = msgs
        for cl in self.clients:
            for p in packets:
                try:
                    cl.send(p)
                    self.sent += 1
                except OSError as e:
                    self.error = str(e)

    def send_frame(self, t: float, targets: list[Target], events, space):
        if not self.cfg.get("enabled", True):
            return
        self._refresh()
        P = self.cfg.get("prefix", "/tracking").rstrip("/")
        S = self.cfg.get("send", {})
        msgs = []
        self.seq += 1
        if S.get("frame", True):
            msgs.append(_msg(f"{P}/frame", self.seq, t, len(targets)))
        if S.get("count", True):
            msgs.append(_msg(f"{P}/count", len(targets)))
        if S.get("events", True):
            for kind, tid in events:
                msgs.append(_msg(f"{P}/{tid}/{kind}", 1))
        for tg in targets:
            b = f"{P}/{tg.id}"
            if S.get("position", True):
                msgs.append(_msg(f"{b}/position", tg.x, tg.y))
                if tg.z is not None:
                    msgs.append(_msg(f"{b}/position3", tg.x, tg.y, tg.z))
            if S.get("norm", True):
                u, v = space.normalize(tg.x, tg.y)
                msgs.append(_msg(f"{b}/norm", u, v))
            if S.get("velocity", True):
                msgs.append(_msg(f"{b}/velocity", tg.vx, tg.vy))
            if S.get("valid", True):
                msgs.append(_msg(f"{b}/valid", 1 if tg.valid else 0))
            if S.get("quality", True):
                msgs.append(_msg(f"{b}/quality", tg.q))
            if S.get("source", True):
                msgs.append(_msg(f"{b}/source", tg.src))
            o = tg.obs
            if o is not None:
                if S.get("bbox") and o.bbox:
                    msgs.append(_msg(f"{b}/bbox", *o.bbox))
                if S.get("area"):
                    msgs.append(_msg(f"{b}/area", o.area))
                if S.get("joints") and o.keypoints is not None:
                    # 17 articulaciones × (u, v, conf), normalizadas en la imagen
                    msgs.append(_msg(f"{b}/joints", *[float(x) for x in o.keypoints.ravel()]))
        self._send_all(msgs)

    def send_status(self, hz: float, status: int):
        if not self.cfg.get("enabled", True):
            return
        P = self.cfg.get("prefix", "/tracking").rstrip("/")
        self._send_all([_msg(f"{P}/system/hz", hz), _msg(f"{P}/system/status", status)])
