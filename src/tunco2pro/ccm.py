"""Convergence-confinement method (GRC + LDP + SCC), closed form.

Ported from TunCO2 v1 ``Stability.py`` / ``Opt3D.py`` (Mohr-Coulomb GRC after
Carranza-Torres & Fairhurst; LDP after Vlachopoulos & Diederichs), replacing the
symbolic ``sympy`` solves with closed-form inverses and a bracketed root finder
(~1000x faster, no complex-number failures).

Units: stresses and moduli in MPa, lengths in m.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, Field
from scipy.optimize import brentq


class Ground(BaseModel):
    p0_mpa: float = Field(5.4, gt=0, description="In-situ stress sigma3 / p0")
    cohesion_mpa: float = Field(0.01, ge=0)
    friction_deg: float = Field(30.0, gt=0, lt=90)
    modulus_mpa: float = Field(500.0, gt=0, description="Rock-mass deformation modulus Em")
    poisson: float = Field(0.25, gt=0, lt=0.5)


class Support(BaseModel):
    radius_m: float = Field(3.64, gt=0, description="Excavation radius r0")
    thickness_m: float = Field(0.252, gt=0)
    concrete_ucs_mpa: float = Field(20.0, gt=0)
    concrete_modulus_mpa: float = Field(30000.0, gt=0)
    concrete_poisson: float = Field(0.2, gt=0, lt=0.5)
    install_distance_m: float = Field(0.0, ge=0, description="Distance behind face xi0")


@dataclass
class CCMResult:
    Pcr: float
    rp_final: float
    u_final: float
    u_face: float
    u_install: float
    k_support: float
    p_support_max: float
    u_support_max: float
    p_mob: float
    u_mob: float
    fos: float
    plastic: bool


def concrete_modulus_v1(fc_mpa: float) -> float:
    """Correlation found in v1 Opt3D.py (9760.9 fc^0.319).

    v1 assigned it to the *rock-mass* modulus Em (finding F8); it is a concrete
    stiffness correlation and is applied to Ec here.
    """
    return 9760.9 * fc_mpa ** 0.319


class GRC:
    def __init__(self, g: Ground, r0: float):
        phi = math.radians(g.friction_deg)
        self.sigma_cm = 2 * g.cohesion_mpa * math.cos(phi) / (1 - math.sin(phi))
        self.k = (1 + math.sin(phi)) / (1 - math.sin(phi))
        self.p0, self.E, self.v, self.r0 = g.p0_mpa, g.modulus_mpa, g.poisson, r0
        self.Pcr = (2 * self.p0 - self.sigma_cm) / (1 + self.k)

    def rp(self, p: float) -> float:
        k, s = self.k, self.sigma_cm
        num = 2 * (self.p0 * (k - 1) + s)
        den = (1 + k) * ((k - 1) * p + s)
        # cohesionless ground (c = 0) with no support: the plastic zone is unbounded; keep it finite
        den = max(den, 1e-9 * num if num > 0 else 1e-12)
        return self.r0 * (num / den) ** (1 / (k - 1))

    def u_elastic(self, p: float) -> float:
        return self.r0 * (1 + self.v) * (self.p0 - p) / self.E

    def u_plastic(self, p: float) -> float:
        v = self.v
        return self.r0 * (1 + v) / self.E * (
            2 * (1 - v) * (self.p0 - self.Pcr) * (self.rp(p) / self.r0) ** 2 - (1 - 2 * v) * (self.p0 - p))

    def u(self, p: float, v1_plastic_branch: bool = False) -> float:
        if v1_plastic_branch or p < self.Pcr:
            return self.u_plastic(p)
        return self.u_elastic(p)


def solve(g: Ground, s: Support, v1_plastic_branch: bool = False) -> CCMResult:
    """Factor of safety of the lining = p_support_max / p_mob.

    ``v1_plastic_branch=True`` uses the plastic GRC branch for all pressures,
    exactly as v1 did; the default uses the elastic branch above Pcr.
    """
    grc = GRC(g, s.radius_m)
    r0 = s.radius_m
    pl = grc.Pcr > 0
    rp_f = grc.rp(0.0) if pl else r0
    u_f = min(grc.u(0.0, v1_plastic_branch), r0)
    u_face = (1 / 3) * math.exp(-0.15 * rp_f / r0) * u_f
    # LDP inverse (x >= 0 behind face)
    x = s.install_distance_m
    u_inst = u_f * (1 - (1 - u_face / u_f) * math.exp(-3 * x / (2 * rp_f)))

    t, Ec, vc = s.thickness_m, s.concrete_modulus_mpa, s.concrete_poisson
    kc = Ec * (r0 ** 2 - (r0 - t) ** 2) / ((1 + vc) * ((1 - 2 * vc) * r0 ** 2 + (r0 - t) ** 2))
    p_smax = s.concrete_ucs_mpa / 2 * (1 - (r0 - t) ** 2 / r0 ** 2)
    u_smax = u_inst + p_smax / kc * r0

    f = lambda p: grc.u(p, v1_plastic_branch) - (p * r0 / kc + u_inst)
    if f(0.0) <= 0:
        p_mob = 0.0
    else:
        p_mob = brentq(f, 0.0, grc.p0, xtol=1e-12)
    u_mob = p_mob * r0 / kc + u_inst
    fos = p_smax / p_mob if p_mob > 0 else math.inf
    return CCMResult(grc.Pcr, rp_f, u_f, u_face, u_inst, kc, p_smax, u_smax, p_mob, u_mob, fos, pl)


def curves(g: Ground, s: Support, n: int = 120, v1_plastic_branch: bool = False) -> dict:
    """Series for plotting GRC, SCC and LDP."""
    r = solve(g, s, v1_plastic_branch)
    grc = GRC(g, s.radius_m)
    ps = [g.p0_mpa * i / (n - 1) for i in range(n)]
    grc_u = [grc.u(p, v1_plastic_branch) for p in ps]
    scc = [[r.u_install, 0.0], [r.u_support_max, r.p_support_max], [max(r.u_final, r.u_support_max) * 1.1, r.p_support_max]]
    xs = [-3 * s.radius_m + 6 * s.radius_m * i / (n - 1) for i in range(n)]
    ldp = []
    for x in xs:
        if x < 0:
            u = r.u_face * math.exp(x / s.radius_m)
        else:
            u = r.u_final * (1 - (1 - r.u_face / r.u_final) * math.exp(-3 * x / (2 * r.rp_final)))
        ldp.append([x, u])
    return {"grc": [[u, p] for u, p in zip(grc_u, ps)], "scc": scc, "ldp": ldp,
            "equilibrium": [r.u_mob, r.p_mob], "result": r.__dict__}
