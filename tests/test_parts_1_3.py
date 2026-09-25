"""Checks against the published TunCO2 papers (Parts 1-3) and the new digitalisation/optimisation layer."""
import math
from pathlib import Path

import pytest

from tunco2pro.alignment import default_zones, from_landxml, straight_with_curve
from tunco2pro.carbon import assess, strategies
from tunco2pro.geometry import route_elements
from tunco2pro.models import ProjectInput, Route
from tunco2pro.optimise import OptimiseInput, ParametricInput, optimise, parametric
from tunco2pro.route import assess_route, optimise_route

EX = Path(__file__).resolve().parents[1] / "examples"


def item(res, name):
    return next(i.kg_per_m for i in res.items if i.element == name)


# ---------------------------------------------------------------- Part 3 published baseline
def test_part3_rail_exemplar_matches_paper():
    """Chen et al. (2026) Part 3, TUST 167, 107028: per-metre baseline of the rail tunnel exemplar."""
    p = ProjectInput.model_validate_json((EX / "part3_metro_case.json").read_text())
    r = assess(p, compat_v1=True)
    published = {"Lining concrete": 2799, "Lining reinforcement": 1335, "Invert backfill": 1126,
                 "Annulus grout": 846, "TBM manufacture (allocated)": 598, "TBM excavation energy": 2504,
                 "Spoil removal": 961}
    for k, v in published.items():
        assert item(r, k) == pytest.approx(v, abs=1.0), k
    assert r.module_totals_kg_per_m()["A4"] == pytest.approx(211, abs=1.0)


# ---------------------------------------------------------------- Part 1: functional units, A5 extensions
def test_functional_units_and_a5_extensions():
    p = ProjectInput()
    p.functional.kind, p.functional.count = "road", 3
    p.tbm.aux_power_kw, p.tbm.aux_hours_per_m, p.tbm.site_diesel_l_per_m = 500, 2, 10
    r = assess(p)
    fu = r.functional_units()
    assert fu["tCO2e per lane-km"] == pytest.approx(r.total_kg_per_m / 3)
    assert item(r, "Auxiliary plant (electric)") == pytest.approx(500 * 2 * 0.85)
    assert item(r, "Site plant diesel") == pytest.approx(10 * 3.378)
    p.tbm.loads.energy_method = "specific_energy"; p.tbm.loads.specific_energy_kwh_m3 = 20
    r2 = assess(p)
    assert r2.intermediate["energy_kWh_per_m"] == pytest.approx(20 * math.pi / 4 * 7.28 ** 2)


def test_combined_levers_below_sum_of_individual():
    p = ProjectInput(); r = assess(p); s = strategies(p, r)
    individual = sum(v for k, v in s["savings_kgCO2e_per_m"].items() if "Logistics" not in k)
    assert 0 < s["combined_design_levers_kgCO2e_per_m"] < individual


# ---------------------------------------------------------------- Part 1/2 digitalisation: alignment, zones, LoD
def test_landxml_line_and_curve():
    al = from_landxml((EX / "sample_alignment.landxml.xml").read_text())
    assert al.start_chainage_m == 1000
    assert al.length_m == pytest.approx(400 + 500 * math.radians(36.8699), rel=2e-3)
    assert al.points[0].z == pytest.approx(-20) and al.points[-1].z < -30


def test_route_totals_equal_sum_of_zones():
    p = ProjectInput(route=Route(alignment=straight_with_curve(1000, 500)))
    r = assess_route(p)
    assert r["total_tCO2e"] == pytest.approx(sum(z["tCO2e"] for z in r["zones"]))
    # cutterhead energy follows each zone's ground, so zones differ; with a ground-independent energy the route
    # average equals the single-section result for the same design
    assert len({round(z["energy_kWh_per_m"], 3) for z in r["zones"]}) > 1
    pf = p.model_copy(deep=True); pf.tbm.loads.energy_method = "forces"
    q = ProjectInput(); q.tbm.loads.energy_method = "forces"
    assert assess_route(pf)["average_kgCO2e_per_m"] == pytest.approx(assess(q).total_kg_per_m, rel=1e-6)
    deep = [z for z in r["zones"] if z["zone"] == "Deep sandstone"][0]
    fair = r["zones"][0]
    assert deep["fos"] < fair["fos"]  # higher in-situ stress -> lower FoS


def test_zone_design_override_changes_carbon():
    p = ProjectInput(route=Route())
    p.route.zones[0].lining_thickness_m = 0.25
    r = assess_route(p)
    assert r["zones"][0]["kgCO2e_per_m"] < r["zones"][1]["kgCO2e_per_m"]


@pytest.mark.parametrize("lod", [200, 300])
def test_lod_quantities_consistent_with_calculation(lod):
    p = ProjectInput(route=Route())
    els, meta = route_elements(p, lod)
    vol = sum(e.volume_m3 for e in els if e.kind in ("lining", "segment", "key"))
    A = assess(ProjectInput()).intermediate["ring_area_m2"]
    assert vol == pytest.approx(A * 1000, rel=0.01)  # joints and chord approximation < 1 %


# ---------------------------------------------------------------- Part 2/3 optimisation
def test_nsga2_with_sls_and_grades():
    o = optimise(OptimiseInput(algorithm="nsga2", discrete_grades=True, u_max_mm=250, fos_min=2.0, pop_size=24, n_gen=15))
    assert o["feasible"]
    grades = set(ProjectInput().criteria.concrete_grades_mpa)
    for s in o["pareto"]:
        assert s["fos"] >= 2.0 - 1e-9 and s["u_mob_m"] * 1000 <= 250 + 1e-6 and s["strength_mpa"] in grades


def test_route_optimisation_saves_carbon():
    o = optimise_route(ProjectInput(route=Route()), pop_size=16, n_gen=8)
    assert o["saving_tCO2e"] > 0 and all(z["feasible"] for z in o["zones"])


def test_parametric_trends_follow_part2():
    rows = parametric(ParametricInput(inner_diameters_m=[6.3], di_over_t=[20], cover_m=[50, 125]))["rows"]
    assert rows[0]["fos"] > rows[1]["fos"]  # deeper -> lower FoS
    big = parametric(ParametricInput(inner_diameters_m=[6.3, 14.1], di_over_t=[20], cover_m=[75]))["rows"]
    assert big[1]["carbon_kg_per_m"] > 4 * big[0]["carbon_kg_per_m"]  # carbon grows ~ D^2
