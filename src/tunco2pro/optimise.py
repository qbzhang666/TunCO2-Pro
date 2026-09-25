"""Low-carbon lining design optimisation (Part 2 and Part 3).

- NSGA-II with two objectives (lining A1-A3 carbon, FoS) as in Part 2, or
  NSGA-III with three (carbon, FoS, convergence) as in Part 3 / v1 Opt3D.py.
- Constraints: ULS FoS >= fos_min; optional SLS convergence u_eq <= u_max;
  optional discrete concrete grades (C25, C32, ...).
- Carbon uses the same factor library as the assessment; the v1 concrete
  stiffness correlation is applied to Ec (v1 wrongly applied it to Em, F8).
- ``parametric()`` reproduces the Part 2 study of FoS vs carbon across tunnel
  diameters, D_i/t ratios and in-situ stress.
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.algorithms.moo.moead import MOEAD
from pymoo.algorithms.moo.spea2 import SPEA2
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.core.problem import ElementwiseProblem
from pymoo.optimize import minimize
from pymoo.util.ref_dirs import get_reference_directions

from .carbon import concrete_ecf, ring_area, steel_ecf
from .ccm import Ground, Support, concrete_modulus_v1, solve
from .factors import FactorLibrary, load_library
from .models import ProjectInput


class OptimiseInput(BaseModel):
    project: ProjectInput = ProjectInput()
    ground: Ground = Ground()
    algorithm: Literal["nsga2", "nsga3", "spea2", "moead"] = Field("nsga3", description="nsga2, spea2, moead: carbon vs FoS (the three algorithms of TunCO2 Part 3, with its SBX/PM operators); nsga3: carbon, FoS and convergence")
    thickness_m: tuple[float, float] = (0.20, 0.45)
    strength_mpa: tuple[float, float] = (30.0, 60.0)
    install_distance_m: tuple[float, float] = (0.0, 6.0)
    discrete_grades: bool = Field(False, description="Restrict f'c to project.criteria.concrete_grades_mpa")
    concrete_modulus_mpa: float = 30000.0
    concrete_poisson: float = 0.2
    modulus_from_strength: bool = Field(True, description="Ec = 9760.9 fc^0.319 (v1 correlation)")
    fos_min: float = Field(1.5, gt=0)
    u_max_mm: float | None = Field(None, gt=0, description="SLS convergence limit")
    pop_size: int = Field(60, ge=8, le=400)
    n_gen: int = Field(40, ge=1, le=500)
    seed: int = 1


def lining_carbon_kg_per_m(p: ProjectInput, t: float, fc: float, lib: FactorLibrary,
                           D_i: float | None = None) -> float:
    q = p.model_copy(update={"concrete": p.concrete.model_copy(update={"strength_mpa": fc})})
    ecf_c, _, _ = concrete_ecf(q, lib)
    ecf_s, _, _ = steel_ecf(q, lib)
    A = ring_area(D_i if D_i is not None else p.geometry.inner_diameter_m, t)
    return A * (ecf_c + p.steel.reinforcement_ratio_pct / 100 * p.steel.density_kg_m3 * ecf_s)


def evaluate(oi: OptimiseInput, t: float, fc: float, xi0: float, lib: FactorLibrary) -> dict:
    r0 = oi.project.geometry.tbm_diameter_m / 2
    Ec = concrete_modulus_v1(fc) if oi.modulus_from_strength else oi.concrete_modulus_mpa
    r = solve(oi.ground, Support(radius_m=r0, thickness_m=t, concrete_ucs_mpa=fc, concrete_modulus_mpa=Ec,
                                 concrete_poisson=oi.concrete_poisson, install_distance_m=xi0))
    return {"thickness_m": t, "strength_mpa": fc, "install_distance_m": xi0,
            "carbon_kg_per_m": lining_carbon_kg_per_m(oi.project, t, fc, lib),
            "fos": min(r.fos, 50.0), "u_mob_m": r.u_mob, "p_mob_mpa": r.p_mob}


class _Problem(ElementwiseProblem):
    def __init__(self, oi: OptimiseInput, lib: FactorLibrary):
        self.oi, self.lib = oi, lib
        self.grades = sorted(oi.project.criteria.concrete_grades_mpa) if oi.discrete_grades else None
        if self.grades:
            g = [x for x in self.grades if oi.strength_mpa[0] <= x <= oi.strength_mpa[1]] or self.grades
            self.grades = g
            fl, fu = 0.0, len(g) - 1e-9
        else:
            fl, fu = oi.strength_mpa
        xl = np.array([oi.thickness_m[0], fl, oi.install_distance_m[0]])
        xu = np.array([oi.thickness_m[1], fu, oi.install_distance_m[1]])
        n_obj = 3 if oi.algorithm == "nsga3" else 2
        n_con = 1 + (1 if oi.u_max_mm else 0)
        self.penalise = oi.algorithm == "moead"          # pymoo's MOEA/D takes no constraints: violations are penalised instead
        super().__init__(n_var=3, n_obj=n_obj, n_ieq_constr=0 if self.penalise else n_con, xl=xl, xu=xu)

    def fc(self, x1: float) -> float:
        return float(self.grades[int(x1)]) if self.grades else float(x1)

    def _evaluate(self, x, out, *args, **kwargs):
        t, x1, xi0 = map(float, x)
        e = evaluate(self.oi, t, self.fc(x1), xi0, self.lib)
        out["F"] = [e["carbon_kg_per_m"], -e["fos"]] + ([e["u_mob_m"]] if self.n_obj == 3 else [])
        g = [self.oi.fos_min - e["fos"]]
        if self.oi.u_max_mm:
            g.append(e["u_mob_m"] * 1000 - self.oi.u_max_mm)
        if self.penalise:
            v = sum(max(0.0, x) for x in g)
            out["F"] = [f + 1e4 * v for f in out["F"]]
        else:
            out["G"] = g


def optimise(oi: OptimiseInput, lib: FactorLibrary | None = None) -> dict:
    lib = (lib or load_library(oi.project.factor_set)).with_overrides(oi.project.factor_overrides)
    prob = _Problem(oi, lib)
    # the two-objective algorithms use the operator settings of TunCO2 v1 (Part 3): SBX (p = 0.9, eta = 10), PM (eta = 10)
    ops = dict(sampling=FloatRandomSampling(), crossover=SBX(prob=0.9, eta=10), mutation=PM(eta=10), eliminate_duplicates=True)
    if oi.algorithm == "nsga2":
        algo = NSGA2(pop_size=oi.pop_size, **ops)
    elif oi.algorithm == "spea2":
        algo = SPEA2(pop_size=oi.pop_size, **ops)
    elif oi.algorithm == "moead":
        algo = MOEAD(ref_dirs=get_reference_directions("das-dennis", 2, n_partitions=max(oi.pop_size - 1, 4)), n_neighbors=15, prob_neighbor_mating=0.7)
    else:
        algo = NSGA3(pop_size=oi.pop_size, ref_dirs=get_reference_directions("das-dennis", 3, n_partitions=8))
    res = minimize(prob, algo, ("n_gen", oi.n_gen), seed=oi.seed, verbose=False)
    sols = []
    if res.X is not None:
        for x in np.atleast_2d(res.X):
            e = evaluate(oi, float(x[0]), prob.fc(float(x[1])), float(x[2]), lib)
            if e["fos"] >= oi.fos_min and (not oi.u_max_mm or e["u_mob_m"] * 1000 <= oi.u_max_mm):
                sols.append(e)
        # de-duplicate (discrete grades can collapse solutions) and sort by carbon
        seen, uniq = set(), []
        for s in sorted(sols, key=lambda s: s["carbon_kg_per_m"]):
            k = (round(s["thickness_m"], 3), round(s["strength_mpa"], 1), round(s["install_distance_m"], 2))
            if k not in seen:
                seen.add(k); uniq.append(s)
        sols = uniq
    g = oi.project.geometry
    base = evaluate(oi, g.lining_thickness_m, oi.project.concrete.strength_mpa, 0.0, lib)
    rec = sols[0] if sols else None
    return {"algorithm": oi.algorithm, "pareto": sols, "baseline": base,
            "baseline_carbon_kg_per_m": base["carbon_kg_per_m"], "recommended": rec,
            "fos_min": oi.fos_min, "u_max_mm": oi.u_max_mm,
            "n_evaluations": int(res.algorithm.evaluator.n_eval), "feasible": bool(sols),
            "message": "" if sols else "No design satisfies the constraints within the bounds."}


# ---------------------------------------------------------------------------
class ParametricInput(BaseModel):
    project: ProjectInput = ProjectInput()
    ground: Ground = Ground(cohesion_mpa=0.5, friction_deg=30, modulus_mpa=2000)
    inner_diameters_m: list[float] = [6.3, 9.0, 14.1]
    di_over_t: list[float] = [18, 20, 22, 25]
    cover_m: list[float] = [50, 75, 100, 125]
    unit_weight_kn_m3: float = 27.0
    strength_mpa: float = 25.0
    install_distance_m: float = 0.0
    overcut_m: float = Field(0.15, ge=0, description="Excavated radius = lining outer radius + overcut")


def parametric(pi: ParametricInput, lib: FactorLibrary | None = None) -> dict:
    """Part 2, Fig. 5 style study: FoS and lining carbon vs D_i, D_i/t and depth."""
    lib = (lib or load_library(pi.project.factor_set)).with_overrides(pi.project.factor_overrides)
    rows = []
    for Di in pi.inner_diameters_m:
        for ratio in pi.di_over_t:
            t = Di / ratio
            r0 = Di / 2 + t + pi.overcut_m
            for H in pi.cover_m:
                g = pi.ground.model_copy(update={"p0_mpa": pi.unit_weight_kn_m3 * H / 1000})
                r = solve(g, Support(radius_m=r0, thickness_m=t, concrete_ucs_mpa=pi.strength_mpa,
                                     concrete_modulus_mpa=concrete_modulus_v1(pi.strength_mpa),
                                     install_distance_m=pi.install_distance_m))
                rows.append({"inner_diameter_m": Di, "di_over_t": ratio, "thickness_m": t, "cover_m": H,
                             "p0_mpa": g.p0_mpa, "fos": min(r.fos, 50.0) if math.isfinite(r.fos) else 50.0,
                             "u_mob_mm": r.u_mob * 1000,
                             "carbon_kg_per_m": lining_carbon_kg_per_m(pi.project, t, pi.strength_mpa, lib, D_i=Di)})
    return {"rows": rows}
