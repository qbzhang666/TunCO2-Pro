"""The six TBM types: ground applicability, engineering models, and what each
changes in the carbon assessment.

Applicability follows the classification of TBM types by ground (ITA terminology:
hard-rock TBMs, soft-ground shields) as consolidated from DAUB (2025), ITA (2000),
JSCE (2016) and EFNARC (2005):
  * rock, categorical: gripper for competent rock; single shield where the rock
    will not take a gripper load (thrust on the rings); double shield does both;
    hard-rock faces are unsupported and at atmospheric pressure;
  * soil, by permeability k: EPB support unaided below about 1e-6 m/s, extended
    by foam/polymer conditioning across 1e-6 to 1e-4 m/s, limited above;
    slurry supports the clean sands and gravels the paste cannot;
  * within the overlap the discriminating property is the fines content
    (< 0.06 mm): EPB needs roughly >= 15 % for a plastic paste; slurry becomes
    limited above about 40 % because the separation plant cannot recover the
    bentonite;
  * multi-mode machines cross the rock/soil divider.
Squeezing/swelling ground and gripper reaction in weak rock are not captured by
k; they are flagged from rock quality instead. The class boundaries are
empirical screening limits, not a substitute for project-specific selection.

Engineering models per type come from Part 3 (type regressions of thrust and
torque on diameter). There is no published mass regression for hard-rock TBMs;
the EPB regression is used with a warning unless a manufacturer mass is entered.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

MachineType = str  # one of TYPES keys


@dataclass(frozen=True)
class TBMType:
    key: str
    label: str
    family: str                 # "hard-rock TBM" | "soft-ground shield" | "multi-mode"
    thrust_reaction: str
    face_support: str
    muck_route: str
    regression_type: str        # key into tbm.THRUST_BY_TYPE / TORQUE_BY_TYPE
    mass_model: str             # "EPB" | "Slurry" | "Multi"
    mass_regression_note: str = ""
    slurry_circuit: bool = False
    model_file: str = ""
    notes: list[str] = field(default_factory=list)


TYPES: dict[str, TBMType] = {t.key: t for t in [
    TBMType("gripper", "Gripper TBM", "hard-rock TBM", "gripper shoes on the rock", "none (unsupported, atmospheric)",
            "muck buckets → belt", "Open TBM", "EPB", "no hard-rock mass regression in Part 3; EPB regression used",
            model_file="gripper.glb", notes=["Needs rock that takes the gripper load", "Face unsupported: inflow controlled by probing and pre-grouting"]),
    TBMType("single_shield", "Single shield TBM", "hard-rock TBM", "on the erected ring", "shield skin only (face unsupported)",
            "muck buckets → chute → belt", "Single Shield TBM", "EPB", "no hard-rock mass regression in Part 3; EPB regression used",
            model_file="single_shield.glb", notes=["Advance stops for ring build"]),
    TBMType("double_shield", "Double shield TBM", "hard-rock TBM", "grippers in competent rock, rings otherwise",
            "shield skin only (face unsupported)", "muck buckets → chute → belt", "Double Shield TBM", "EPB",
            "no hard-rock mass regression in Part 3; EPB regression used", model_file="double_shield.glb",
            notes=["Carries both reaction systems: longer, heavier shield", "Continuous boring while the ring is built in gripper mode"]),
    TBMType("epb", "EPB shield", "soft-ground shield", "on the erected ring", "earth pressure (spoil, conditioned)",
            "screw conveyor → belt", "EPB TBM", "EPB", model_file="epb.glb",
            notes=["Foam/polymer conditioning extends the range to coarser ground (conditioning agents not in the carbon model)"]),
    TBMType("slurry", "Slurry shield", "soft-ground shield", "on the erected ring", "pressurised bentonite slurry",
            "slurry pipeline → separation plant", "Slurry TBM", "Slurry", slurry_circuit=True, model_file="slurry.glb",
            notes=["Separation plant energy: enter kWh/m3 (not in the Part 3 model)"]),
    TBMType("multi_mode", "Multi-mode shield", "multi-mode", "on the erected ring", "earth pressure or slurry (switchable)",
            "screw conveyor and slurry circuit fitted", "Multi-mode TBM", "Multi",
            "no regression; the larger of the EPB and slurry regressions is used", slurry_circuit=True,
            model_file="multi_mode.glb", notes=["Carries both circuits: heaviest and most expensive machine",
                                                "Mode changes cost time; separation plant needed in slurry mode"]),
]}

ORDER = list(TYPES)

# --------------------------------------------------------------------------- applicability
OK, MARGINAL, NO = "suitable", "marginal", "unsuitable"
RANK = {OK: 0, MARGINAL: 1, NO: 2}


EPB_UNAIDED_K, EPB_CONDITIONED_K = 1e-6, 1e-4       # m/s (DAUB 2025, EFNARC 2005)
SLURRY_MIN_K = 1e-6                                   # below: fine-grained, separation-limited
EPB_MIN_FINES, SLURRY_MAX_FINES = 15.0, 40.0          # % finer than 0.06 mm (DAUB 2025)


def _soil_rules(k: float | None, fines: float | None = None) -> dict[str, tuple[str, str]]:
    out = {}
    if k is None and fines is None:
        return {"epb": (MARGINAL, "soil permeability and fines not given"), "slurry": (MARGINAL, "soil permeability and fines not given"),
                "multi_mode": (OK, "soil")}
    # EPB
    if k is None:
        epb = (OK, "no permeability given; judged on fines")
    elif k <= EPB_UNAIDED_K:
        epb = (OK, f"k = {k:.0e} m/s: spoil forms a support medium unaided")
    elif k <= EPB_CONDITIONED_K:
        epb = (OK, f"k = {k:.0e} m/s: EPB with foam/polymer conditioning")
    else:
        epb = (MARGINAL, f"k = {k:.0e} m/s: above the conditioned EPB range (application limited)")
    if fines is not None and fines < EPB_MIN_FINES and epb[0] == OK:
        epb = (MARGINAL, epb[1] + f"; fines {fines:.0f} % < {EPB_MIN_FINES:.0f} %: spoil will not form a plastic paste without fines addition")
    out["epb"] = epb
    # slurry
    if fines is not None and fines > SLURRY_MAX_FINES:
        sl = (MARGINAL, f"fines {fines:.0f} % > {SLURRY_MAX_FINES:.0f} %: separation plant cannot recover the bentonite")
    elif k is not None and k < SLURRY_MIN_K:
        sl = (MARGINAL, f"k = {k:.0e} m/s: fine-grained ground, separation-limited")
    else:
        sl = (OK, (f"k = {k:.0e} m/s" if k is not None else "fines within limit") + ": pressurised bentonite support")
    out["slurry"] = sl
    out["multi_mode"] = (OK, "covers both closed-face modes")
    return out


def applicability(ground_kind: str | None, rock_quality: str | None = None, k_m_s: float | None = None,
                  water_head_m: float | None = None, fines_pct: float | None = None) -> dict[str, dict]:
    """Suitability of each type for one zone: {type: {"rating", "reason"}}."""
    r: dict[str, tuple[str, str]] = {}
    gk = ground_kind or "unknown"
    if gk == "rock":
        q = rock_quality or "fractured"
        r["gripper"] = {"competent": (OK, "competent rock takes the gripper load"),
                        "fractured": (MARGINAL, "fractured rock: gripper reaction uncertain"),
                        "weak": (NO, "weak rock will not take a gripper load")}[q]
        r["single_shield"] = (OK, "thrust on the rings") if q != "competent" else (OK, "works; slower than gripper modes")
        r["double_shield"] = (OK, "gripper mode in competent rock") if q == "competent" else (OK, "ring mode where grippers will not hold")
        closed = {"competent": (MARGINAL, "closed face not needed in stable rock; slow, high cutter wear"),
                  "fractured": (MARGINAL, "possible; abrasive wear and cutter changes under pressure"),
                  "weak": (OK, "weak rock: closed face gives face support")}[q]
        r["epb"] = closed
        r["slurry"] = closed
        r["multi_mode"] = (OK, "open (rock) mode") if q != "competent" else (OK, "open (rock) mode; over-specified for this ground")
        wet = water_head_m is not None and water_head_m > 10 and (k_m_s is None or k_m_s >= 1e-6)
        if wet:
            for t in ("gripper", "single_shield", "double_shield"):
                if r[t][0] == OK:
                    r[t] = (MARGINAL, r[t][1] + f"; {water_head_m:.0f} m water head on an unsupported face (pre-grouting)")
            for t in ("epb", "slurry", "multi_mode"):
                r[t] = (OK, f"closed face holds {water_head_m:.0f} m water head")
    elif gk == "soil":
        for t in ("gripper", "single_shield", "double_shield"):
            r[t] = (NO, "soil needs a supported face")
        r.update(_soil_rules(k_m_s, fines_pct))
    elif gk == "mixed":
        for t in ("gripper", "double_shield"):
            r[t] = (NO, "mixed face: soil in the face, no gripper reaction")
        r["single_shield"] = (MARGINAL, "mixed face with an unsupported face")
        soil = _soil_rules(k_m_s, fines_pct)
        r["epb"] = (OK if soil["epb"][0] == OK else MARGINAL, "mixed face; " + soil["epb"][1])
        r["slurry"] = (OK if soil["slurry"][0] == OK else MARGINAL, "mixed face; " + soil["slurry"][1])
        r["multi_mode"] = (OK, "designed for mixed and changing ground")
    else:
        return {t: {"rating": MARGINAL, "reason": "ground kind not given"} for t in ORDER}
    return {t: {"rating": r[t][0], "reason": r[t][1]} for t in ORDER}


def zone_applicability(z) -> dict[str, dict]:
    return applicability(getattr(z, "ground_kind", None), getattr(z, "rock_quality", None),
                         getattr(z, "permeability_m_s", None), getattr(z, "water_head_m", None), getattr(z, "fines_pct", None))


def route_applicability(zones) -> dict:
    """Per zone ratings and, per type, the share of route length it suits."""
    rows, L = [], sum(z.ch_to - z.ch_from for z in zones) or 1.0
    share = {t: {OK: 0.0, MARGINAL: 0.0, NO: 0.0} for t in ORDER}
    for z in zones:
        a = zone_applicability(z)
        rows.append({"zone": z.name, "ch_from": z.ch_from, "ch_to": z.ch_to, "ground_kind": getattr(z, "ground_kind", None),
                     "unit": getattr(z, "unit", None), "ratings": a})
        for t in ORDER:
            share[t][a[t]["rating"]] += (z.ch_to - z.ch_from) / L
    worst = {t: max((r["ratings"][t]["rating"] for r in rows), key=RANK.get) if rows else MARGINAL for t in ORDER}
    return {"zones": rows, "share": share, "worst": worst,
            "recommended": sorted(ORDER, key=lambda t: (RANK[worst[t]], -share[t][OK]))}


def catalogue() -> list[dict]:
    return [asdict(t) for t in TYPES.values()]


def compare(p, compat_v1: bool = False) -> dict:
    """Assess the same project with each of the six machines (type regressions for
    thrust and torque, type mass model) and rate each against the route's ground."""
    from .carbon import apply_machine_type, assess
    rows = []
    app = route_applicability(p.route.zones) if p.route else None
    for key in ORDER:
        q = p.model_copy(update={"tbm": p.tbm.model_copy(update={"machine_type": key})})
        q = apply_machine_type(q, force_regressions=True)
        r = assess(q.model_copy(update={"route": None}), compat_v1=compat_v1)
        a5 = {i.element: i.kg_per_m for i in r.items if i.module == "A5"}
        rows.append({"type": key, "label": TYPES[key].label, "family": TYPES[key].family,
                     "thrust_MN": r.intermediate["thrust_MN"], "torque_MNm": r.intermediate["torque_MNm"],
                     "energy_kWh_per_m": r.intermediate["energy_kWh_per_m"], "mass_t": r.intermediate["tbm_mass_t"],
                     "a5_items": a5, "a5_kg_per_m": sum(a5.values()), "total_kg_per_m": r.total_kg_per_m,
                     "total_tCO2e": r.total_kg_per_m * p.tunnel_length_m / 1000,
                     "rating": app["worst"][key] if app else None,
                     "suitable_share": app["share"][key][OK] if app else None,
                     "warnings": [w for w in r.warnings if TYPES[key].label in w]})
    feasible = [x for x in rows if x["rating"] in (None, OK)]
    best = min(feasible, key=lambda x: x["total_kg_per_m"])["type"] if feasible else None
    return {"types": rows, "applicability": app, "lowest_carbon_suitable": best,
            "basis": "Thrust and torque from the Part 3 type regressions at the project TBM diameter; "
                     "energy by the method set in the project; A1-A4 unchanged across types."}
