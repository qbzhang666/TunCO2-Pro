"""TBM thrust, torque, excavation energy and machine mass (v1 'TBM Performance').

Ported one-to-one from the DAX measures Empirical/Analytical Thrust & Torque,
Energy and TBM Production. Units follow v1: thrust in MN, torque in MN.m,
energy in kWh per metre of advance.
"""
from __future__ import annotations

import math

from .models import TBM, TBMLoads

TORQUE_BY_TYPE = {  # MN.m, D in m
    "Double Shield TBM": lambda D: 38.12 * D ** 2.3546 / 1000,
    "EPB TBM": lambda D: 13.438 * D ** 3.154 / 1000,
    "Open TBM": lambda D: (1089.3 * D - 4188.8) / 1000,
    "Single Shield TBM": lambda D: 187.7 * D ** 1.6390 / 1000,
    "Slurry TBM": lambda D: 442.51 * math.exp(0.2925 * D) / 1000,
}
TORQUE_BY_TYPE["Multi-mode TBM"] = lambda D: max(TORQUE_BY_TYPE["EPB TBM"](D), TORQUE_BY_TYPE["Slurry TBM"](D))
THRUST_BY_TYPE = {  # MN
    "Double Shield TBM": lambda D: (6435.1 * D - 20032 + 2862.8 * D ** 1.3569) / 1000,
    "EPB TBM": lambda D: 8972.6 * math.exp(0.2208 * D) / 1000,
    "Open TBM": lambda D: (1777.1 * D + 377.7) / 1000,
    "Single Shield TBM": lambda D: 1459.8 * D ** 1.4156 / 1000,
    "Slurry TBM": lambda D: 10269 * math.exp(0.1997 * D) / 1000,
}
# no regression for multi-mode machines: the larger of the two closed-face regressions
THRUST_BY_TYPE["Multi-mode TBM"] = lambda D: max(THRUST_BY_TYPE["EPB TBM"](D), THRUST_BY_TYPE["Slurry TBM"](D))


def reference_pressure_kpa(D: float) -> float:
    """Reference JSCE control pressure for the 'regression_pressure' models: axis depth 2D, water table 3 m
    below surface, unit weight 20 kN/m3, K0 = 0.5, dp = 20 kPa. The Part 3 type regressions are taken to
    hold at this condition; departures from it follow the support pressure."""
    z0 = 2 * D
    u = 9.81 * max(z0 - 3.0, 0.0)
    return 0.5 * (20 * z0 - u) + u + 20.0


def face_friction_factor(p: TBMLoads, D: float) -> float:
    """MN.m of cutterhead torque per kPa of chamber pressure: friction on the closed part of the face and
    the bulkhead side, the pressure term of the analytical relation (medium friction p.f)."""
    return math.pi / 12 * (1 + p.f_deltap) * p.f * (1 - p.opening) * D ** 3 / 1000


def torque_mnm(p: TBMLoads, D: float) -> float:
    m = p.torque_model
    if m == "empirical":
        return p.alpha_t * D ** 3 / 1000
    if m == "empirical_type":
        return TORQUE_BY_TYPE[p.tbm_type_torque](D)
    if m == "regression_pressure":
        dp = (p.support_pressure_kpa if p.support_pressure_kpa is not None else reference_pressure_kpa(D)) - reference_pressure_kpa(D)
        return max(TORQUE_BY_TYPE[p.tbm_type_torque](D) + face_friction_factor(p, D) * dp, 0.1 * TORQUE_BY_TYPE[p.tbm_type_torque](D))
    if m == "user":
        return p.user_torque_mnm
    # face and bulkhead friction: the cutterhead turns against the chamber pressure (K0 gamma H unless a
    # support pressure is given, e.g. the JSCE control pressure of face.py)
    p_face = p.support_pressure_kpa if p.support_pressure_kpa is not None else p.K0 * p.gamma * p.H
    k1 = math.pi / 12 * ((1 + p.f_deltap) * p.f * p_face * (1 - p.opening) + p.kq * p.opening * p.tau)
    k2 = math.pi / 4 * (p.K0 + 1) * p.f * p.gamma * p.H * p.W
    k3 = p.gamma * p.H * p.Db * p.Lb * p.fc_cut * p.Rb * p.Nb
    return (k1 * D ** 3 + k2 * D ** 2 + k3) / 1000


def thrust_mn(p: TBMLoads, D: float) -> float:
    m = p.thrust_model
    if m == "empirical":
        return p.alpha_f * D ** 2 / 1000
    if m == "empirical_type":
        return THRUST_BY_TYPE[p.tbm_type_thrust](D)
    if m == "regression_pressure":  # face pressure acts on the full face area
        dp = (p.support_pressure_kpa if p.support_pressure_kpa is not None else reference_pressure_kpa(D)) - reference_pressure_kpa(D)
        return max(THRUST_BY_TYPE[p.tbm_type_thrust](D) + math.pi / 4 * D ** 2 * dp / 1000, 0.1 * THRUST_BY_TYPE[p.tbm_type_thrust](D))
    if m == "user":
        return p.user_thrust_mn
    if m == "xie2024":
        up, lo = xie2024_thrust_mn(p, D, p.mass_t or 7 * D ** 2.21)
        return {"upper": up, "lower": lo}.get(p.thrust_bound, 0.5 * (up + lo))
    gw = 9.8  # unit weight of water, kN/m3
    rc = p.advance_mm_min / (p.rpm * p.lc)
    face = (p.K * p.gamma * p.H + p.K * p.pq + gw * p.H_w) * (1 - p.hatch) + p.pc * p.hatch
    if p.soil_type == "Sandy Soil":
        k1 = math.pi / 4 * face - (1 / 3) * p.f * (p.gamma - gw) * p.L * (2 + p.K0)
        k2 = math.pi / 2 * p.f * (p.gamma - gw) * (1 + p.K0) * p.H * p.L
        k3 = p.f * p.G + p.ns * p.Ws * p.mus + p.mua * p.Wa
        denom3 = math.pi / 4 * face - (1 / 3) * p.f * (p.gamma - gw) * p.L * (2 + p.K0)
        a3 = math.pi / 4 * (p.K * p.gamma * p.H + p.K * p.pq) * (1 - p.hatch) / denom3
        face_eff = (p.K * (p.gamma - gw) * p.H + p.K * p.pq + gw * p.H_w) * (1 - p.hatch) + p.pc * p.hatch
        denom4 = math.pi / 4 * face_eff - (1 / 3) * p.f * (p.gamma - gw) * p.L * (2 + p.K0)
        a4 = (math.pi / 4 * gw * p.H_w * (1 - p.hatch) + p.pc * p.hatch) / denom4
        return (k1 * (a3 * rc + a4) * D ** 2 + k2 * D + k3) / 1000
    # Clay
    k1 = math.pi / 4 * face
    k2 = math.pi * p.L * p.c
    k3 = p.ns * p.Ws * p.mus + p.mua * p.Wa
    face_eff = (p.K * (p.gamma - gw) * p.H + p.K * p.pq + gw * p.H_w) * (1 - p.hatch) + p.pc * p.hatch
    b1 = (p.K * (p.gamma - gw) * p.H + p.K * p.pq) * (1 - p.hatch) / face_eff
    b2 = (gw * p.H_w * (1 - p.hatch) + p.pc * p.hatch) / face_eff
    return (k1 * (b1 * rc + b2) * D ** 2 + k2 * D + k3) / 1000


def energy_kwh_per_m(p: TBMLoads, D: float) -> float:
    """Work of thrust over 1 m plus cutterhead rotation work per metre of advance."""
    F = thrust_mn(p, D)
    T = torque_mnm(p, D)
    revs_per_m = p.rpm / (p.advance_mm_min * 0.001)
    kj = F * 1000 * 1.0 + 2 * math.pi * T * 1000 * revs_per_m
    return kj / 3600.0


def tbm_mass_kg(tbm: TBM, D: float, v1: bool = False) -> float:
    """Machine mass for manufacture (A5) and shield friction.

    Finding F5, resolved: 7 D^2.21 (EPB) and 6.62 D^2.18 (slurry) are masses in tonnes. They reproduce the
    machines of Xie et al. (2024): a 6.98 m EPB of 510 t (7 D^2.21 = 512 t) and a 12.0 m Mixshield of
    1274 t (6.62 D^2.18 = 1491 t). v1 divided by 9.8 as if converting a weight, understating mass ~10x;
    that is kept only for v1 compatibility.
    """
    g = 9.8 if v1 else 1.0
    if tbm.mass_model == "EPB":
        return 7 * D ** 2.21 * 1000 / g
    if tbm.mass_model == "Slurry":
        return 6.62 * D ** 2.18 * 1000 / g
    if tbm.mass_model == "Multi":
        return max(7 * D ** 2.21, 6.62 * D ** 2.18) * 1000 / g
    return tbm.user_mass_t * 1000


# ---------------------------------------------------------------------------------------------------------
# BIM-to-Thrust relation of Xie et al. (2024), closed form for one ground zone
K_CRITICAL_M_S = 5e-5   # 5.0e-3 cm/s: water analysed separately only above this permeability


def xie2024_thrust_mn(p: TBMLoads, D: float, mass_t: float) -> tuple[float, float]:
    """(upper, lower) total thrust F_T = F_s + F_w + F_f (Xie et al. 2024, Eqs. 5-10) for a uniform zone.

    F_s: soil force on the face, K0 sigma_v (upper) or Ka sigma_v - 2 c sqrt(Ka) (lower), Ka = K0/(1 + sin phi');
    F_w: water force, only where k >= k_critical, the soil then taken at effective stress;
    F_f: shield friction, f (W_TBM + L R sigma_v (2 + 4 K0)) - vertical stress on the upper half, K0 sigma_v
         all round, integrated over the shield of length L.
    sigma_v averaged over a circular face equals its value at the axis for a linear profile.
    """
    A = math.pi / 4 * D ** 2
    R = D / 2
    sv = p.gamma * p.H
    u = 9.81 * p.H_w
    separate = p.permeability_m_s is not None and p.permeability_m_s >= K_CRITICAL_M_S
    s_eff = max(sv - u, 0.0) if separate else sv
    K0 = p.K0
    sinphi = min(max(1 - K0, 0.0), 0.99)            # Jaky, K0 = 1 - sin(phi')
    Ka = K0 / (1 + sinphi)
    Fs_up = K0 * s_eff * A
    Fs_lo = max(Ka * s_eff - 2 * p.c * math.sqrt(Ka), 0.0) * A
    Fw = u * A if separate else 0.0
    L = p.shield_length_m or 1.25 * D
    Ff = p.shield_friction * (mass_t * 9.81 + L * R * s_eff * (2 + 4 * K0))
    return (Fs_up + Fw + Ff) / 1000, (Fs_lo + Fw + Ff) / 1000
