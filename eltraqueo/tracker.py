# SPDX-License-Identifier: GPL-3.0-or-later
"""Capa 4 — IDs estables, suavizado, velocidad, entradas y salidas.

IDs:  1–99  identidad física (tag de LED IR o UWB)
      101–199 objetivos sin identidad (manchas, cuerpos)
Una candidata con tag usa siempre el ID del tag (así queda lista la fusión).
"""
from __future__ import annotations

import math

from .contracts import Candidate, Target


class Tracker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.targets: dict[int, Target] = {}
        self._next_anon = 101
        self.events: list[tuple[str, int]] = []

    def reset(self):
        for tid in list(self.targets):
            if self.targets[tid].announced_enter:
                self.events.append(("exit", tid))
        self.targets.clear()
        self._next_anon = 101

    # -------------------------------------------------------------------
    def _merge(self, cands: list[Candidate]) -> list[Candidate]:
        """Une candidatas de varias entradas que caen en el mismo lugar."""
        r = float(self.cfg.get("merge_radius", 0.4))
        out: list[Candidate] = []
        for c in sorted(cands, key=lambda c: -c.q):
            for m in out:
                if (c.tag is None or m.tag is None or c.tag == m.tag) and \
                        math.hypot(c.x - m.x, c.y - m.y) <= r and c.obs and m.obs \
                        and c.obs.sensor != m.obs.sensor:
                    wt = m.q + c.q
                    m.x = (m.x * m.q + c.x * c.q) / max(wt, 1e-6)
                    m.y = (m.y * m.q + c.y * c.q) / max(wt, 1e-6)
                    m.q = min(1.0, max(m.q, c.q) + 0.15)   # más vistas, más confianza
                    m.tag = m.tag or c.tag
                    if m.src != c.src:
                        m.src = 3
                    break
            else:
                out.append(Candidate(c.t, c.src, c.x, c.y, c.z, c.q, c.tag, c.obs))
        return out

    def _new_id(self, tag):
        if tag and 1 <= tag <= 99:
            return tag
        for _ in range(99):
            tid = self._next_anon
            self._next_anon = 101 if self._next_anon >= 199 else self._next_anon + 1
            if tid not in self.targets:
                return tid
        return None

    # -------------------------------------------------------------------
    def update(self, cands: list[Candidate] | None, t: float):
        c = self.cfg
        if cands:
            cands = self._merge(cands)
            free = list(range(len(cands)))
            used: set[int] = set()

            # 1. por tag
            for i in list(free):
                tag = cands[i].tag
                if tag and tag in self.targets:
                    self._apply(self.targets[tag], cands[i], t)
                    used.add(tag)
                    free.remove(i)

            # 2. por cercanía (voraz, pares ordenados por distancia)
            R = float(c.get("match_radius", 0.9))
            pairs = []
            for tid, tg in self.targets.items():
                if tid in used:
                    continue
                dt = max(0.0, t - tg.last_seen)
                px, py = tg.x + tg.vx * min(dt, 0.3), tg.y + tg.vy * min(dt, 0.3)
                for i in free:
                    if cands[i].tag and tg.tag and cands[i].tag != tg.tag:
                        continue
                    d = math.hypot(cands[i].x - px, cands[i].y - py)
                    if d <= R:
                        pairs.append((d, tid, i))
            pairs.sort()
            for d, tid, i in pairs:
                if tid in used or i not in free:
                    continue
                tg = self.targets[tid]
                self._apply(tg, cands[i], t)
                used.add(tid)
                free.remove(i)
                # Una mancha anónima que recibe tag adopta el ID del tag (fusión)
                tag = cands[i].tag
                if tag and 1 <= tag <= 99 and tid != tag and tag not in self.targets:
                    del self.targets[tid]
                    if tg.announced_enter:
                        self.events.append(("exit", tid))
                        tg.announced_enter = False
                    tg.id = tag
                    self.targets[tag] = tg
                    used.add(tag)

            # 3. nuevos
            for i in free:
                if len(self.targets) >= int(c.get("max_targets", 8)):
                    break
                tid = self._new_id(cands[i].tag)
                if tid is None or tid in self.targets:
                    continue
                cd = cands[i]
                tg = Target(id=tid, x=cd.x, y=cd.y, z=cd.z, q=cd.q, src=cd.src, tag=cd.tag,
                            last_seen=t, born=t, obs=cd.obs, hits=1)
                self.targets[tid] = tg

        # vencimientos
        inv, grace = float(c.get("invalid_after", 0.25)), float(c.get("grace", 2.0))
        need = int(c.get("confirm_hits", 3))
        for tid in list(self.targets):
            tg = self.targets[tid]
            age = t - tg.last_seen
            tg.valid = age <= inv
            if not tg.valid:
                tg.vx *= 0.8
                tg.vy *= 0.8
            if not tg.confirmed and tg.hits >= need:
                tg.confirmed = True
            if tg.confirmed and not tg.announced_enter:
                tg.announced_enter = True
                self.events.append(("enter", tid))
            if age > grace or (not tg.confirmed and age > inv * 2):
                if tg.announced_enter:
                    self.events.append(("exit", tid))
                del self.targets[tid]

    def _apply(self, tg: Target, cd: Candidate, t: float):
        s = float(self.cfg.get("smoothing", 0.5))
        s = min(max(s, 0.0), 0.95)
        dt = t - tg.last_seen
        nx = s * tg.x + (1 - s) * cd.x
        ny = s * tg.y + (1 - s) * cd.y
        if dt > 1e-3:
            vx, vy = (nx - tg.x) / dt, (ny - tg.y) / dt
            tg.vx = 0.7 * tg.vx + 0.3 * vx
            tg.vy = 0.7 * tg.vy + 0.3 * vy
        tg.x, tg.y = nx, ny
        if cd.z is not None:
            tg.z = cd.z if tg.z is None else s * tg.z + (1 - s) * cd.z
        tg.q = 0.7 * tg.q + 0.3 * cd.q
        tg.src = cd.src
        tg.tag = tg.tag or cd.tag
        tg.obs = cd.obs
        tg.last_seen = t
        tg.hits += 1

    def published(self) -> list[Target]:
        return sorted((t for t in self.targets.values() if t.confirmed), key=lambda t: t.id)

    def pop_events(self):
        ev, self.events = self.events, []
        return ev
