"""Ground movement from volume loss: the Gaussian settlement trough, zone by zone.

Transverse trough (Peck 1969; O'Reilly and New 1982):

    S(y)   = S_max exp(-y^2 / 2 i^2),      i = K z0,      S_max = V_L (pi D^2 / 4) / (sqrt(2 pi) i)

with V_L the volume loss as a fraction of the excavated area, z0 the axis depth and K the trough-width parameter
(about 0.5 in clays, 0.25 to 0.35 in sands and gravels; O'Reilly and New 1982; Mair and Taylor 1997). Horizontal
movement is directed at the axis, H(y) = (y / z0) S(y), so the horizontal strain is

    eps_h(y) = S(y) / z0 (1 - y^2 / i^2)      (compression under the centreline, tension beyond y = i)

and the slope dS/dy is largest at the point of inflection y = i, where it is 0.607 S_max / i. The longitudinal
profile ahead of and behind the face is the cumulative normal (Attewell and Woodman 1982):

    S(x) = S_max Phi(-x / i)                  (x ahead of the face; 0.5 S_max at the face for an unsupported face)

The volume loss is entered (project or zone) or estimated from the ground and the machine. Typical values for
closed-face machines driven with the face pressure at K0 are 0.2 to 0.5 % in sands and 0.5 to 1 % in clays
(Mair and Taylor 1997; Mair 2008); the estimate here uses the upper part of each band and raises it where the face
pressure is set below K0 or the machine has no face support in soil. The trough is a screening tool: it says
whether a zone needs a settlement assessment and gives the surface response against which a numerical model of
that zone (Chapter 7, Section 7.6.3) is compared. Damage screening follows Rankin (1988): maximum settlement
and slope of the trough against the four risk categories.

References: Peck (1969) 7th ICSMFE; O'Reilly and New (1982) Tunnelling 82; Attewell and Woodman (1982) Ground
Engineering 15(8); Rankin (1988) Geological Society Eng. Geol. Special Publ. 5; Mair and Taylor (1997) 14th
ICSMFE; Mair (2008) Geotechnique 58(9).
"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

SQRT_2PI = math.sqrt(2 * math.pi)
CLOSED_FACE = ("epb", "slurry", "multi_mode")

# Rankin (1988): (max settlement mm, max slope) upper bounds of each category
RANKIN = [(10.0, 1 / 500, 1, "negligible: superficial damage unlikely"),
          (50.0, 1 / 200, 2, "possible superficial damage, unlikely to have structural significance"),
          (75.0, 1 / 50, 3, "expected superficial damage and possible structural damage to buildings; possible damage to rigid pipelines"),
          (math.inf, math.inf, 4, "expected structural damage to buildings; expected damage to rigid pipelines and possible damage to other pipelines")]


class SettlementCriteria(BaseModel):
    """Volume-loss settlement screening for the route (project-wide; a zone may override V_L and K)."""
    volume_loss_pct: float | None = Field(None, ge=0, le=20, description="Volume loss V_L, % of the excavated area; blank = estimated per zone from the ground, the machine and the face-pressure mode")
    trough_k: float | None = Field(None, gt=0, lt=1.5, description="Trough-width parameter K (i = K z0); blank = per zone from the fines content (0.5 clay, 0.4 silt, 0.3 sand, 0.25 rock)")
    s_max_mm: float = Field(25.0, gt=0, description="SLS: maximum surface settlement over the axis")
    slope_max: float = Field(1 / 500, gt=0, description="SLS: maximum slope of the trough (1/500 is the boundary of Rankin's negligible category)")


def trough_k(z) -> float:
    """Trough-width parameter K from the ground description of a zone (O'Reilly and New 1982; Mair and Taylor 1997)."""
    k = getattr(z, "trough_k", None)
    if k:
        return k
    if z.ground_kind == "rock":
        return 0.25
    f = z.fines_pct
    if f is None:
        return 0.35 if z.ground_kind == "mixed" else 0.4
    return 0.5 if f >= 35 else (0.4 if f >= 15 else 0.3)


def estimate_volume_loss(z, machine_type: str, face_mode: str = "K0") -> tuple[float, str]:
    """Volume loss (%) and its basis, from the ground kind, fines, machine family and face-pressure mode."""
    v = getattr(z, "volume_loss_pct", None)
    if v is not None:
        return v, "zone input"
    closed = machine_type in CLOSED_FACE
    if z.ground_kind == "rock":
        return 0.1, "rock: nominal"
    f = z.fines_pct
    if f is None:
        base, soil = (1.0, "mixed face") if z.ground_kind == "mixed" else (0.75, "soil, fines unknown")
    elif f >= 35:
        base, soil = 1.0, "clay"
    elif f >= 15:
        base, soil = 0.75, "silty soil"
    else:
        base, soil = 0.5, "sand and gravel"
    if not closed:
        return round(2 * base, 3), f"{soil}, no face support"
    if face_mode != "K0":
        return round(1.5 * base, 3), f"{soil}, closed face below K0 pressure"
    return base, f"{soil}, closed face at K0"


def trough(z0_m: float, d_m: float, volume_loss_pct: float, k: float) -> dict:
    """Trough parameters for one section: i, S_max and the derived slope, strain and extent."""
    i = k * z0_m
    area = math.pi * d_m ** 2 / 4
    s_max = volume_loss_pct / 100 * area / (SQRT_2PI * i)          # m
    return {"i_m": i, "s_max_mm": s_max * 1000, "slope_max": s_max / (i * math.sqrt(math.e)),
            "eps_h_compression": s_max / z0_m, "eps_h_tension": 2 * s_max * math.exp(-1.5) / z0_m,
            "half_width_m": 2.5 * i, "lost_volume_m3_per_m": volume_loss_pct / 100 * area}


def transverse(y_m: float, z0_m: float, i_m: float, s_max_m: float) -> tuple[float, float, float, float]:
    """Settlement, horizontal movement (towards the axis), slope and horizontal strain at offset y (metres)."""
    s = s_max_m * math.exp(-y_m ** 2 / (2 * i_m ** 2))
    return s, y_m / z0_m * s, -y_m / i_m ** 2 * s, s / z0_m * (1 - y_m ** 2 / i_m ** 2)


def longitudinal(x_ahead_m: float, i_m: float, s_max_m: float) -> float:
    """Settlement over the axis at a distance x ahead of the face (negative behind it)."""
    return s_max_m * 0.5 * math.erfc(x_ahead_m / (i_m * math.sqrt(2)))


def volume_loss_from_smax(s_max_mm: float, i_m: float, d_m: float) -> float:
    """Volume loss (%) implied by a measured maximum settlement (the inverse of `trough`, for back-analysis)."""
    return s_max_mm / 1000 * SQRT_2PI * i_m / (math.pi * d_m ** 2 / 4) * 100


def damage_category(s_max_mm: float, slope: float) -> tuple[int, str]:
    """Rankin (1988) risk category from the maximum settlement and slope (the worse of the two governs)."""
    for s_lim, g_lim, cat, text in RANKIN:
        if s_max_mm <= s_lim and slope <= g_lim:
            return cat, text
    return 4, RANKIN[-1][3]


def profiles(z0_m: float, i_m: float, s_max_m: float, n: int = 61) -> dict:
    """Sampled transverse (to 3 i) and longitudinal (-3 i to +3 i about the face) profiles, in mm and m."""
    ys = [-3 * i_m + 6 * i_m * j / (n - 1) for j in range(n)]
    xs = [-3 * i_m + 6 * i_m * j / (n - 1) for j in range(n)]
    tv = [transverse(y, z0_m, i_m, s_max_m) for y in ys]
    return {"y_m": ys, "s_mm": [t[0] * 1000 for t in tv], "h_mm": [t[1] * 1000 for t in tv],
            "eps_h_pct": [t[3] * 100 for t in tv], "x_ahead_m": xs,
            "s_long_mm": [longitudinal(x, i_m, s_max_m) * 1000 for x in xs]}


def zone_settlement(p, z, with_profiles: bool = False) -> dict:
    """Volume-loss screening of one ground zone of a project."""
    crit = p.settlement
    vl, basis = (crit.volume_loss_pct, "project input") if crit.volume_loss_pct is not None and getattr(z, "volume_loss_pct", None) is None \
        else estimate_volume_loss(z, p.tbm.machine_type, p.face.earth_coefficient)
    k = crit.trough_k if crit.trough_k is not None and getattr(z, "trough_k", None) is None else trough_k(z)
    t = trough(z.cover_m, p.geometry.tbm_diameter_m, vl, k)
    cat, text = damage_category(t["s_max_mm"], t["slope_max"])
    out = {"volume_loss_pct": vl, "basis": basis, "K": k, **t, "damage_category": cat, "damage_text": text,
           "s_ok": t["s_max_mm"] <= crit.s_max_mm, "slope_ok": t["slope_max"] <= crit.slope_max}
    if with_profiles:
        out["profiles"] = profiles(z.cover_m, t["i_m"], t["s_max_mm"] / 1000)
    return out
