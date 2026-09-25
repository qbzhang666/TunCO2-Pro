"""Cutterhead torque and excavation energy from the working mechanics of the head.

Energy per metre of advance is the work of the thrust over one metre plus the
work of the cutterhead torque over the revolutions needed to advance one metre:

    E = F * 1 + 2 pi T / p            (p = penetration per revolution, m/rev)
    SE = E / A                        (specific energy, per m3 excavated)

so every torque term that does not scale with penetration (friction, paste
shear, bearing and seals) is paid once per revolution, and its share of the
energy grows as penetration falls. The torque is built from what resists the
head turning:

  soft-ground shields (EPB, slurry)
    T_cut  = e_c A p / (2 pi)                       tools cutting the face; e_c = kappa * tau_f
    T_face = n_f (1 - xi) (2 pi / 3) R^3 tau_m      closed part of the face and the bulkhead side
    T_rim  = pi D W R tau_m                         gauge / rim of width W running in the overcut
    with tau_m the shear resistance of the medium in contact with the steel:
      EPB    tau_m = tau_0 + tan(delta) (p_c - u)   conditioned paste: undrained strength plus a
                                                    small friction on the effective chamber stress
      slurry tau_m = tau_s + psi tan(delta_s) (p_c - u)
                                                    tau_s: drag of the slurry-spoil mixture on spokes and in
                                                    the lower chamber where coarse spoil settles; psi: share of
                                                    the closed face bearing on the ground through the filter
                                                    cake (bentonite alone has a yield stress of tens of Pa)
  hard-rock TBMs (discs)
    F_n = FPI * p per disc, rolling/normal force ratio CC = tan(phi/2), cos(phi) = (R_d - p)/R_d
    T_cut = CC * N_c * F_n * r_bar,  r_bar ~ 0.55 R  (uniform track spacing plus crowded gauge)
  all heads
    T = (T_cut + T_face + T_rim) / (1 - eta),  eta = bearing, seal and gear losses

Parameters are given as (low, central, high) with the physical basis in RANGES.
They vary from project to project with ground, conditioning, head design and
operation; ranges() propagates them to P10 / P50 / P90 torque and energy.
The EPB paste parameters are calibrated on operating records of a large-diameter EPB drive; the others rest on
the physical basis given and published machine data, and should be calibrated against the project's own records.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

GAMMA_W = 9.81


@dataclass(frozen=True)
class R3:
    low: float
    central: float
    high: float
    basis: str = ""


RANGES: dict[str, dict[str, R3]] = {
    "epb": {
        "opening": R3(0.25, 0.35, 0.45, "open area of soft-ground heads; mixed-ground heads nearer the low end"),
        "n_faces": R3(1.5, 1.8, 2.0, "face plus bulkhead side in paste; <2 where the chamber is not full"),
        "tau0_kpa": R3(4.0, 8.0, 20.0, "undrained shear strength of conditioned spoil (plastic paste); central value calibrated "
                                       "on operating records of a large-diameter EPB drive"),
        "tan_delta": R3(0.01, 0.02, 0.06, "friction on effective chamber stress; foam keeps it small, clogging raises it; "
                                          "central value from the recorded torque-pressure slope of the same drive"),
        "rim_w_over_d": R3(0.05, 0.07, 0.09, "gauge / rim width relative to diameter"),
        "kappa": R3(2.0, 3.0, 5.0, "cutting energy per m3 as a multiple of the ground's shear strength (drag tools)"),
        "pen_soil_mm": R3(10.0, 20.0, 35.0, "penetration per revolution in soil"),
        "pen_rock_mm": R3(5.0, 10.0, 20.0, "penetration per revolution where the face is weak rock"),
        "eta_mech": R3(0.05, 0.08, 0.12, "bearing, seal and gearbox losses"),
        "ec_rock_factor": R3(0.6, 1.0, 1.5, "scatter of rock cutting energy (discs on a mixed-ground head) about EC_ROCK_KJ_M3"),
    },
    "slurry": {
        "opening": R3(0.25, 0.35, 0.45, "open area"),
        "n_faces": R3(1.0, 1.2, 1.5, "face side; bulkhead side partly in slurry"),
        "psi": R3(0.10, 0.20, 0.30, "share of the closed face bearing on the ground through the filter cake"),
        "tau_s_kpa": R3(2.0, 5.0, 10.0, "drag of the slurry-spoil mixture on spokes and settled spoil in the chamber invert"),
        "tan_delta": R3(0.30, 0.40, 0.50, "steel-soil friction at the face"),
        "min_sigma_kpa": R3(10.0, 20.0, 40.0, "effective face support at least the overpressure margin"),
        "rim_w_over_d": R3(0.05, 0.07, 0.09, "gauge / rim width relative to diameter"),
        "kappa": R3(2.0, 3.0, 5.0, "cutting energy as a multiple of shear strength"),
        "pen_soil_mm": R3(15.0, 25.0, 40.0, "penetration per revolution in sand and gravel"),
        "pen_rock_mm": R3(5.0, 10.0, 20.0, "penetration per revolution in weak rock"),
        "eta_mech": R3(0.05, 0.08, 0.12, "bearing, seal and gearbox losses"),
        "ec_rock_factor": R3(0.6, 1.0, 1.5, "scatter of rock cutting energy about EC_ROCK_KJ_M3"),
    },
    "hardrock": {
        "disc_radius_m": R3(0.216, 0.241, 0.254, "17-20 inch discs"),
        "spacing_mm": R3(75.0, 85.0, 95.0, "track spacing"),
        "fn_kn": R3(200.0, 250.0, 300.0, "operating normal force per disc (80-90 % of rating)"),
        "fpi_competent": R3(25.0, 40.0, 60.0, "field penetration index, kN/cutter per mm/rev, competent massive rock"),
        "fpi_fractured": R3(12.0, 22.0, 35.0, "FPI in jointed / blocky rock"),
        "fpi_weak": R3(4.0, 8.0, 15.0, "FPI in weak or faulted rock (penetration then limited by torque and muck)"),
        "pen_cap_mm": R3(10.0, 15.0, 20.0, "operational cap on penetration per revolution"),
        "r_bar": R3(0.50, 0.55, 0.60, "torque-weighted mean cutter radius / R"),
        "eta_mech": R3(0.05, 0.08, 0.12, "bearing, seal and gearbox losses"),
    },
}
RANGES["multi_mode"] = RANGES["epb"]

# cutting energy of discs on a soft-ground or mixed-ground head meeting rock, kJ/m3 (about 11, 5.5 and 2.2 kWh/m3):
# the disc-cutting part of hard-rock specific energy at the penetrations such heads reach
EC_ROCK_KJ_M3 = {"competent": 40e3, "fractured": 20e3, "weak": 8e3}


def family(machine_type: str | None) -> str:
    if machine_type in ("gripper", "single_shield", "double_shield"):
        return "hardrock"
    if machine_type == "slurry":
        return "slurry"
    return "epb"


def central(fam: str) -> dict[str, float]:
    return {k: v.central for k, v in RANGES[fam].items()}


@dataclass
class Face:
    """Ground at the face of one zone."""
    p_c_kpa: float = 200.0            # chamber / support pressure at the axis
    u_kpa: float = 100.0              # pore-water pressure at the axis
    sigma_v_eff_kpa: float = 200.0    # effective vertical stress at the axis
    cohesion_kpa: float = 10.0
    phi_deg: float = 30.0
    rock_fraction: float = 0.0        # share of the face in rock
    rock_quality: str = "fractured"   # competent | fractured | weak


def torque_energy(fam: str, D: float, f: Face, q: dict[str, float], thrust_mn: float = 0.0) -> dict:
    """Torque components (MN.m), penetration (mm/rev) and energy (kWh/m, kWh/m3) for one parameter set."""
    R, A = D / 2, math.pi / 4 * D ** 2
    if fam == "hardrock":
        fpi = q[f"fpi_{f.rock_quality}"] if f"fpi_{f.rock_quality}" in q else q["fpi_fractured"]
        p_mm = min(q["fn_kn"] / fpi, q["pen_cap_mm"])
        fn = fpi * p_mm                                        # kN per disc at that penetration
        phi = math.acos(max((q["disc_radius_m"] - p_mm / 1000) / q["disc_radius_m"], -1.0))
        cc = math.tan(phi / 2)
        n_c = R * 1000 / q["spacing_mm"] + 8                   # face tracks plus gauge discs
        t_cut = cc * n_c * fn * q["r_bar"] * R / 1000          # MN.m
        comps = {"cutting": t_cut, "face_friction": 0.0, "rim": 0.0}
        thrust_mn = thrust_mn or n_c * fn / 1000
    else:
        rf = min(max(f.rock_fraction, 0.0), 1.0)
        p_mm = (1 - rf) * q["pen_soil_mm"] + rf * q["pen_rock_mm"]
        sig_eff_c = max(f.p_c_kpa - f.u_kpa, 0.0)
        if fam == "slurry":
            tau_m = q["tau_s_kpa"] + q["psi"] * q["tan_delta"] * max(sig_eff_c, q["min_sigma_kpa"])
        else:
            tau_m = q["tau0_kpa"] + q["tan_delta"] * sig_eff_c
        tau_f = f.cohesion_kpa + f.sigma_v_eff_kpa * math.tan(math.radians(f.phi_deg))
        e_c_soil = q["kappa"] * tau_f                          # kJ/m3
        e_c_rock = EC_ROCK_KJ_M3.get(f.rock_quality, EC_ROCK_KJ_M3["fractured"]) * q["ec_rock_factor"]
        e_c = (1 - rf) * e_c_soil + rf * e_c_rock
        t_cut = e_c * A * p_mm / 1000 / (2 * math.pi) / 1000   # MN.m
        g_face = q["n_faces"] * (1 - q["opening"]) * 2 * math.pi / 3 * R ** 3
        t_face = g_face * tau_m / 1000
        t_rim = math.pi * D * q["rim_w_over_d"] * D * R * tau_m / 1000
        comps = {"cutting": t_cut, "face_friction": t_face, "rim": t_rim}
    t_work = sum(comps.values())
    T = t_work / (1 - q["eta_mech"])
    comps["mechanical"] = T - t_work
    e_rot = 2 * math.pi * T * 1000 / (p_mm / 1000) / 3600      # kWh per m
    e_thr = thrust_mn * 1000 / 3600
    return {"torque_MNm": T, "components_MNm": comps, "penetration_mm_rev": p_mm,
            "energy_kWh_per_m": e_rot + e_thr, "rotation_kWh_per_m": e_rot, "thrust_kWh_per_m": e_thr,
            "specific_energy_kWh_m3": (e_rot + e_thr) / A}


def ranges(fam: str, D: float, f: Face, thrust_mn: float = 0.0, n: int = 400, seed: int = 7) -> dict:
    """P10 / P50 / P90 of torque and energy with every parameter sampled from a triangular
    distribution over (low, central, high); plus the all-central result."""
    rng = np.random.default_rng(seed)
    spec = RANGES[fam]
    T, E, SE = [], [], []
    for _ in range(n):
        q = {k: float(rng.triangular(v.low, v.central, v.high)) if v.high > v.low else v.central for k, v in spec.items()}
        r = torque_energy(fam, D, f, q, thrust_mn)
        T.append(r["torque_MNm"]); E.append(r["energy_kWh_per_m"]); SE.append(r["specific_energy_kWh_m3"])
    pct = lambda x: [float(np.percentile(x, k)) for k in (10, 50, 90)]  # noqa: E731
    return {"central": torque_energy(fam, D, f, central(fam), thrust_mn),
            "torque_MNm_p10_p50_p90": pct(T), "energy_kWh_per_m_p10_p50_p90": pct(E),
            "specific_energy_kWh_m3_p10_p50_p90": pct(SE)}


def face_from_zone(z, p_c_kpa: float | None, rock_fraction: float | None = None) -> Face:
    u = GAMMA_W * (z.water_head_m or 0.0)
    sv = z.unit_weight_kn_m3 * z.cover_m
    if rock_fraction is None:
        rock_fraction = getattr(z, "rock_fraction", None)
    rf = rock_fraction if rock_fraction is not None else (1.0 if z.ground_kind == "rock" else 0.5 if z.ground_kind == "mixed" else 0.0)
    return Face(p_c_kpa=p_c_kpa if p_c_kpa is not None else sv, u_kpa=u, sigma_v_eff_kpa=max(sv - u, 0.0),
                cohesion_kpa=z.cohesion_mpa * 1000, phi_deg=z.friction_deg, rock_fraction=rf,
                rock_quality=z.rock_quality or "fractured")


def face_from_loads(L, fam: str) -> Face:
    """Face for a single-section project from the analytical load inputs (depth, weight, water, K0, c)."""
    if L.cutterhead_face:
        return Face(**L.cutterhead_face)
    u = GAMMA_W * (L.H_w or 0.0)
    sv = L.gamma * L.H
    phi = math.degrees(math.asin(min(max(1 - (L.K0 or 0.5), 0.0), 0.95)))
    pc = L.support_pressure_kpa if L.support_pressure_kpa is not None else L.pc
    return Face(p_c_kpa=pc, u_kpa=u, sigma_v_eff_kpa=max(sv - u, 0.0), cohesion_kpa=L.c, phi_deg=phi,
                rock_fraction=1.0 if fam == "hardrock" else 0.0, rock_quality=L.cutterhead_rock_quality)


def equivalent_friction(machine_type: str | None) -> float:
    """Central-value torque per kPa of effective chamber stress, expressed as the medium friction f of the
    face-only relation dT/dp = pi/12 (1 - xi) f D^3 (tbm.face_friction_factor): includes the bulkhead side, the rim
    and the losses, so both torque routes rise with pressure at the same rate."""
    fam = family(machine_type)
    if fam == "hardrock":
        return 0.0
    q = central(fam)
    mu = q["tan_delta"] * (q["psi"] if fam == "slurry" else 1.0)
    # (n_f (1 - xi) pi/12 D^3 + pi W/D D^3 / 2) / ((1 - xi) pi/12 D^3)
    geo = q["n_faces"] + 6 * q["rim_w_over_d"] / (1 - q["opening"])
    return mu * geo / (1 - q["eta_mech"])


def evaluate(machine_type: str | None, D: float, f: Face, thrust_mn: float, overrides: dict | None = None,
             band: bool = True) -> dict:
    """Central result with user overrides of the central values, and the P10-P90 band over RANGES.
    Hard-rock heads take the thrust from the disc forces; soft-ground heads the thrust given."""
    fam = family(machine_type)
    q = central(fam) | {k: float(v) for k, v in (overrides or {}).items() if k in RANGES[fam]}
    th = 0.0 if fam == "hardrock" else thrust_mn
    out = torque_energy(fam, D, f, q, th)
    out["family"] = fam
    if band:
        rg = ranges(fam, D, f, th, n=200)
        out.update({k: v for k, v in rg.items() if k != "central"})
    return out


def range_table() -> list[dict]:
    """RANGES as rows for documentation and the UI."""
    return [{"family": fam, "parameter": k, "low": v.low, "central": v.central, "high": v.high, "basis": v.basis}
            for fam, d in RANGES.items() if fam != "multi_mode" for k, v in d.items()]
