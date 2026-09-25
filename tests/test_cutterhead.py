"""Cutterhead mechanics: torque components, energy per metre and the parameter bands."""
import math

from tunco2pro import cutterhead as ch
from tunco2pro.models import ProjectInput


def test_energy_identity_and_components():
    f = ch.Face(p_c_kpa=180, u_kpa=120, sigma_v_eff_kpa=150, cohesion_kpa=10, phi_deg=30)
    r = ch.torque_energy("epb", 7.25, f, ch.central("epb"), thrust_mn=20)
    T, p = r["torque_MNm"], r["penetration_mm_rev"] / 1000
    assert math.isclose(r["energy_kWh_per_m"], (20e3 + 2 * math.pi * T * 1e3 / p) / 3600, rel_tol=1e-9)
    c = r["components_MNm"]
    assert math.isclose(sum(c.values()), T, rel_tol=1e-9)
    assert c["face_friction"] > c["cutting"]          # soft ground: friction, not cutting, sets the torque


def test_bands_ordered_and_bracket_central():
    f = ch.Face(250, 150, 220, 50, 35, rock_fraction=0.8, rock_quality="fractured")
    r = ch.ranges("epb", 9.19, f, 12.56)
    lo, mid, hi = r["torque_MNm_p10_p50_p90"]
    assert lo < mid < hi and lo < r["central"]["torque_MNm"] < hi
    # a published 9.19 m EPB in limestone ran at a mean torque of 7.6 MN.m (Heliyon 2024)
    assert lo < 7.6 < hi


def test_torque_scales_with_d_cubed_and_slurry_below_epb():
    f = ch.Face(200, 130, 150, 0, 33)
    t7 = ch.torque_energy("epb", 7.25, f, ch.central("epb"))["torque_MNm"]
    t15 = ch.torque_energy("epb", 15.6, f, ch.central("epb"))["torque_MNm"]
    assert 7 < t15 / t7 < 11                          # (15.6/7.25)^3 = 10 for the friction terms
    assert ch.torque_energy("slurry", 7.25, f, ch.central("slurry"))["torque_MNm"] < t7


def test_hard_rock_disc_model():
    comp = ch.torque_energy("hardrock", 10.45, ch.Face(rock_fraction=1, rock_quality="competent"), ch.central("hardrock"))
    frac = ch.torque_energy("hardrock", 10.45, ch.Face(rock_fraction=1, rock_quality="fractured"), ch.central("hardrock"))
    assert comp["penetration_mm_rev"] < frac["penetration_mm_rev"]
    assert comp["specific_energy_kWh_m3"] > frac["specific_energy_kWh_m3"]
    assert 5 < frac["specific_energy_kWh_m3"] < 40


def test_components_method_in_assess_and_overrides():
    from tunco2pro.carbon import assess
    p = ProjectInput()
    p.tbm.machine_type = "epb"
    p.tbm.loads.energy_method = "components"
    r = assess(p)
    cut = r.intermediate["cutterhead"]
    assert cut and math.isclose(r.intermediate["energy_kWh_per_m"], cut["energy_kWh_per_m"])
    p.tbm.loads.cutterhead_overrides = {"tau0_kpa": 25.0}
    assert assess(p).intermediate["torque_MNm"] > cut["torque_MNm"]


def test_examples_carry_energy_band():
    from tunco2pro.gisbim import compare_examples
    for e in compare_examples()["examples"]:
        b = e["excavation_energy_band"]["specific_energy_kWh_m3"]
        assert b[0] < b[1] < b[2]
    assert ch.range_table()[0]["basis"]


def test_face_friction_defaults_match_cutterhead():
    from tunco2pro.face import FaceSupport
    fs = FaceSupport()
    assert abs(fs.epb_friction - ch.equivalent_friction("epb")) < 0.005
    assert abs(fs.slurry_friction - ch.equivalent_friction("slurry")) < 0.005
    assert ProjectInput().tbm.loads.energy_method == "components"
