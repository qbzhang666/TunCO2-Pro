"""Independent hand calculations of the v1 default case (slicer values in the .pbix)."""
import math
import pytest
from tunco2pro.carbon import assess, strategies, ring_area
from tunco2pro.models import ProjectInput
from tunco2pro import tbm

from pathlib import Path
from tunco2pro.factors import load_library

EX = Path(__file__).resolve().parents[1] / "examples"
P = ProjectInput.model_validate_json((EX / "pbix_default_case.json").read_text())  # v1 factor set
Di, t, Dt = 6.6, 0.30, 7.28
A = math.pi / 4 * ((Di + 2 * t) ** 2 - Di ** 2)


def item(res, name):
    return next(i.kg_per_m for i in res.items if i.element == name)


def test_lining_concrete_and_steel():
    r = assess(P)
    assert r.intermediate["concrete_ecf_kg_m3"] == pytest.approx(450.0)  # user points 30:300,40:400,50:500 at 45 MPa
    assert item(r, "Lining concrete") == pytest.approx(A * 450.0)
    assert item(r, "Lining reinforcement") == pytest.approx(A * 0.0173 * 7800 * 1.591)


def test_grout_backfill():
    r = assess(P)
    Ag = math.pi / 4 * (Dt ** 2 - (Di + 2 * t) ** 2)
    assert item(r, "Annulus grout") == pytest.approx(Ag * 200)
    rr, th = Di / 2, math.radians(86)
    seg = math.pi * rr ** 2 * 86 / 360 - rr ** 2 * math.sin(th / 2) * math.cos(th / 2)
    assert item(r, "Invert backfill") == pytest.approx(seg * 451.2)


def test_a4_lining():
    r = assess(P)
    mass_kg = A * 2500 + A * 0.0173 * 7800
    assert item(r, "Lining delivery") == pytest.approx(mass_kg * 60 * 0.106 * 0.001)


def test_energy_and_tbm():
    Pf = P.model_copy(deep=True)
    Pf.tbm.loads.energy_method = "forces"      # the v1 route; the default is now the cutterhead mechanics
    r = assess(Pf)
    L = Pf.tbm.loads
    assert assess(P, compat_v1=True).intermediate["energy_kWh_per_m"] == pytest.approx(
        (tbm.thrust_mn(L, Dt) * 1000 + 2 * math.pi * L.rpm * tbm.torque_mnm(L, Dt) / (L.advance_mm_min * 0.001) * 1000) * 0.000277778, rel=1e-5)
    e = (tbm.thrust_mn(L, Dt) * 1000 + 2 * math.pi * L.rpm * tbm.torque_mnm(L, Dt) / (L.advance_mm_min * 0.001) * 1000) * 0.000277778
    assert r.intermediate["energy_kWh_per_m"] == pytest.approx(e, rel=1e-5)
    assert item(r, "TBM excavation energy") == pytest.approx(e * 0.92, rel=1e-5)
    assert item(assess(P, compat_v1=True), "Spoil removal") == pytest.approx(math.pi / 4 * Dt ** 2 * 0.296 * 100 * 1.3)
    assert item(r, "TBM manufacture (allocated)") == pytest.approx(1100 * 1000 * 1.85 / 3400)  # Mass_Type = User Define
    q = P.model_copy(deep=True); q.tbm.mass_model = "EPB"
    assert item(assess(q, compat_v1=True), "TBM manufacture (allocated)") == pytest.approx(7 * Dt ** 2.21 * 1000 / 9.8 * 1.85 / 3400)
    assert item(assess(q), "TBM manufacture (allocated)") == pytest.approx(7 * Dt ** 2.21 * 1000 * 1.85 / 3400)   # F5 resolved


def test_compat_v1_tbm_transport_and_fitout():
    r = assess(P, compat_v1=True)
    assert item(r, "TBM transport") == pytest.approx(1100 * (40 * 0.106 + 30 * 0.107) * 0.001)
    assert item(r, "Fit-out") == 0.0


def test_totals_consistent():
    r = assess(P); d = r.to_dict()
    assert sum(d["modules_kgCO2e_per_m"].values()) == pytest.approx(d["total_kgCO2e_per_m"])
    assert d["total_tCO2e"] == pytest.approx(d["total_kgCO2e_per_m"] * P.tunnel_length_m / 1000)


def test_database_regression_and_override():
    p = P.model_copy(deep=True); p.concrete.ecf_mode = "database"
    r = assess(p); assert 200 < r.intermediate["concrete_ecf_kg_m3"] < 600
    p2 = P.model_copy(deep=True); p2.factor_overrides = {"grid.vic": 0.5}
    assert item(assess(p2), "TBM excavation energy") == pytest.approx(item(assess(P), "TBM excavation energy") * 0.5 / 0.92)


def test_strategies_positive():
    s = strategies(P, assess(P))["savings_kgCO2e_per_m"]
    assert all(v >= 0 for v in s.values())
    assert s["Reduce lining thickness"] == pytest.approx(
        (ring_area(Di, 0.30) - ring_area(Di, 0.25)) * (450 + 0.0173 * 7800 * 1.591))


# ---------------------------------------------------------------- current factor set
C = ProjectInput()


def test_current_set_sources():
    lib = load_library("current")
    assert lib.value("grid.vic") == pytest.approx(0.74 + 0.11)       # NGA 2026 scope 2 + 3
    assert lib.by_name("steel", "Reinforcing steel - NEFD default").value == 3.65
    assert lib.nefd_concrete_ecf(45)[0] == 621 and lib.nefd_concrete_ecf(40)[0] == 556
    assert lib.nefd_concrete_ecf(45, "average")[0] == 326


def test_current_default_case():
    r = assess(C)
    assert item(r, "Lining concrete") == pytest.approx(A * 621)
    assert item(r, "Lining reinforcement") == pytest.approx(A * 0.0173 * 7800 * 3.65)
    assert item(r, "TBM excavation energy") == pytest.approx(r.intermediate["energy_kWh_per_m"] * 0.85)
    assert item(r, "Spoil removal") == pytest.approx(math.pi / 4 * Dt ** 2 * 2.8 * 100 * 0.07926)
    assert not any("not in the current factor set" in w for w in r.warnings)


def test_v1_names_are_mapped_in_current_set():
    p = C.model_copy(deep=True)
    p.transport.lining[0].mode = "Road, articulated truck"
    r = assess(p)
    assert any("Road, articulated truck" in w for w in r.warnings)
    assert item(r, "Lining delivery") == pytest.approx(item(assess(C), "Lining delivery"))
