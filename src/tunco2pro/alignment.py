"""Alignment and ground zones along the route (Part 1-2 digitalisation layer).

The alignment is a 3D polyline sampled by chainage (straight + circular arcs from
LandXML are densified). Ground zones are chainage intervals with their own
overburden and rock-mass parameters, so carbon and stability are evaluated
zone by zone and aggregated for the route (Part 2: "fixed variables" = alignment,
chainage, overburden, strata; "design variables" = t, f'c, x0).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AlignmentPoint(BaseModel):
    x: float
    y: float
    z: float = 0.0


class Alignment(BaseModel):
    name: str = "Alignment"
    start_chainage_m: float = 0.0
    points: list[AlignmentPoint] = Field(default_factory=lambda: [
        AlignmentPoint(x=0, y=0, z=-25), AlignmentPoint(x=0, y=1000, z=-30)])

    @model_validator(mode="after")
    def _check(self):
        if len(self.points) < 2:
            raise ValueError("Alignment needs at least two points")
        return self

    # --- geometry --------------------------------------------------------
    def _arr(self) -> np.ndarray:
        return np.array([[p.x, p.y, p.z] for p in self.points], dtype=float)

    def cumulative(self) -> np.ndarray:
        P = self._arr()
        d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        return d + self.start_chainage_m

    @property
    def length_m(self) -> float:
        c = self.cumulative()
        return float(c[-1] - c[0])

    @property
    def end_chainage_m(self) -> float:
        return float(self.cumulative()[-1])

    def frame(self, ch: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Point, tangent T, horizontal normal N, up U at chainage ch."""
        P = self._arr(); c = self.cumulative()
        ch = min(max(ch, c[0]), c[-1])
        i = int(np.clip(np.searchsorted(c, ch, side="right") - 1, 0, len(P) - 2))
        seg = P[i + 1] - P[i]
        L = np.linalg.norm(seg) or 1.0
        T = seg / L
        pt = P[i] + T * (ch - c[i])
        N = np.cross(T, [0, 0, 1.0])
        if np.linalg.norm(N) < 1e-9:
            N = np.array([1.0, 0, 0])
        N = N / np.linalg.norm(N)
        U = np.cross(N, T)
        return pt, T, N, U

    def as_polyline(self, step: float = 10.0) -> list[list[float]]:
        c = self.cumulative()
        out = []
        for ch in np.arange(c[0], c[-1] + 1e-9, step):
            out.append([float(ch)] + self.frame(ch)[0].tolist())
        return out


def straight_with_curve(length_m: float = 1000.0, radius_m: float | None = None, depth_start: float = -25.0,
                        depth_end: float = -30.0, step: float = 5.0) -> Alignment:
    """Convenience alignment: straight, or a single horizontal arc of given radius."""
    n = max(2, int(length_m / step) + 1)
    s = np.linspace(0, length_m, n)
    if radius_m:
        th = s / radius_m
        x = radius_m * (1 - np.cos(th)); y = radius_m * np.sin(th)
    else:
        x = np.zeros_like(s); y = s
    z = depth_start + (depth_end - depth_start) * s / length_m
    return Alignment(points=[AlignmentPoint(x=float(a), y=float(b), z=float(c)) for a, b, c in zip(x, y, z)])


def from_landxml(xml_text: str, depth_m: float = -25.0, step: float = 5.0) -> Alignment:
    """Parse the first LandXML <Alignment> (Line and Curve elements; spirals as chords).

    LandXML stores northing before easting ("N E"). A <Profile>/<ProfAlign> with
    <PVI> points sets elevations; otherwise ``depth_m`` is used.
    """
    root = ET.fromstring(xml_text)
    ns = {"l": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda t: f"l:{t}") if ns else (lambda t: t)
    al = root.find(f".//{q('Alignment')}", ns)
    if al is None:
        raise ValueError("No <Alignment> element found")
    sta0 = float(al.get("staStart", 0) or 0)

    def ne(el):
        a = [float(v) for v in (el.text or "").split()]
        return np.array([a[1], a[0]])  # (E, N)

    pts: list[np.ndarray] = []
    geom = al.find(q("CoordGeom"), ns)
    for el in list(geom) if geom is not None else []:
        tag = el.tag.split("}")[-1]
        s = el.find(q("Start"), ns); e = el.find(q("End"), ns)
        if s is None or e is None:
            continue
        S, E = ne(s), ne(e)
        if tag == "Curve" and el.find(q("Center"), ns) is not None:
            C = ne(el.find(q("Center"), ns))
            r = np.linalg.norm(S - C)
            a0 = math.atan2(*(S - C)[::-1]); a1 = math.atan2(*(E - C)[::-1])
            cw = (el.get("rot", "ccw").lower() == "cw")
            da = a1 - a0
            if cw and da > 0: da -= 2 * math.pi
            if not cw and da < 0: da += 2 * math.pi
            n = max(2, int(abs(da) * r / step))
            for k in range(n + 1):
                a = a0 + da * k / n
                pts.append(C + r * np.array([math.cos(a), math.sin(a)]))
        else:
            pts += [S, E]
    if len(pts) < 2:
        raise ValueError("Alignment has no Line/Curve geometry")
    # de-duplicate consecutive points
    P = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - P[-1]) > 1e-6:
            P.append(p)
    P = np.array(P)
    ch = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))] + sta0
    z = np.full(len(P), depth_m)
    pvis = al.findall(f".//{q('PVI')}", ns)
    if len(pvis) >= 2:
        pv = np.array([[float(v) for v in (x.text or "").split()[:2]] for x in pvis])
        z = np.interp(ch, pv[:, 0], pv[:, 1])
    return Alignment(name=al.get("name", "Alignment"), start_chainage_m=sta0,
                     points=[AlignmentPoint(x=float(p[0]), y=float(p[1]), z=float(h)) for p, h in zip(P, z)])


class GroundZone(BaseModel):
    """A chainage interval with uniform ground and (optionally) its own lining design."""
    name: str = "Zone"
    ch_from: float
    ch_to: float
    cover_m: float = Field(25.0, gt=0, description="Axis depth z0: ground surface to tunnel axis (cover to crown C = z0 - D/2)")
    unit_weight_kn_m3: float = Field(27.0, gt=0)
    cohesion_mpa: float = Field(0.5, ge=0)
    friction_deg: float = Field(30.0, gt=0, lt=90)
    modulus_mpa: float = Field(2000.0, gt=0)
    poisson: float = Field(0.25, gt=0, lt=0.5)
    # optional design overrides for this zone
    lining_thickness_m: float | None = None
    concrete_strength_mpa: float | None = None
    reinforcement_ratio_pct: float | None = None
    install_distance_m: float = Field(0.0, ge=0)
    # ground description for TBM selection (tbm_types.applicability)
    ground_kind: Literal["rock", "soil", "mixed"] | None = None
    rock_quality: Literal["competent", "fractured", "weak"] | None = None
    permeability_m_s: float | None = Field(None, gt=0, description="Coefficient of permeability k")
    fines_pct: float | None = Field(None, ge=0, le=100, description="Fines content, % finer than 0.06 mm (soil)")
    water_head_m: float | None = Field(None, ge=0, description="Pore-water head above the tunnel axis (u_w = gamma_w x head)")
    unit: str | None = Field(None, description="Geological unit code, e.g. from a long section")
    face_fractions: dict[str, float] | None = None
    rock_fraction: float | None = Field(None, ge=0, le=1, description="Share of the face in rock (cutterhead energy); None -> from ground_kind")
    volume_loss_pct: float | None = Field(None, ge=0, le=20, description="Volume loss V_L for this zone, %; None -> project value or estimate (settlement.py)")
    trough_k: float | None = Field(None, gt=0, lt=1.5, description="Trough-width parameter K for this zone; None -> project value or from the fines content")

    @property
    def p0_mpa(self) -> float:
        return self.unit_weight_kn_m3 * self.cover_m / 1000.0

    @property
    def length_m(self) -> float:
        return self.ch_to - self.ch_from


def default_zones(length_m: float = 1000.0, start: float = 0.0) -> list[GroundZone]:
    """Three illustrative zones (fair, weak fault zone, deep sandstone) for a new route."""
    a, b = start + 0.4 * length_m, start + 0.75 * length_m
    return [
        GroundZone(name="Siltstone (fair)", ch_from=start, ch_to=a, cover_m=25, cohesion_mpa=0.6, friction_deg=32, modulus_mpa=3000,
                   ground_kind="rock", rock_quality="fractured"),
        GroundZone(name="Fault zone (weak)", ch_from=a, ch_to=b, cover_m=80, cohesion_mpa=0.05, friction_deg=25, modulus_mpa=1000,
                   ground_kind="rock", rock_quality="weak", water_head_m=40),
        GroundZone(name="Deep sandstone", ch_from=b, ch_to=start + length_m, cover_m=200, cohesion_mpa=0.5, friction_deg=30, modulus_mpa=5000,
                   ground_kind="rock", rock_quality="competent"),
    ]
