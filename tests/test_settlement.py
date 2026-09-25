import math

import pytest

from tunco2pro.alignment import GroundZone
from tunco2pro.gisbim import example_project
from tunco2pro.route import assess_route
from tunco2pro.settlement import (damage_category, estimate_volume_loss, longitudinal, profiles, transverse, trough, trough_k,
                                  volume_loss_from_smax, zone_settlement)


def test_trough_closed_form():
    # z0 = 20 m, D = 8 m, V_L = 1 %, K = 0.5: i = 10 m, S_max = 0.01 * 50.27 / (2.5066 * 10) = 20.05 mm
    t = trough(20.0, 8.0, 1.0, 0.5)
    assert t["i_m"] == pytest.approx(10.0)
    assert t["s_max_mm"] == pytest.approx(20.05, abs=0.01)
    assert t["slope_max"] == pytest.approx(0.6065 * 0.02005 / 10, rel=1e-3)
    assert volume_loss_from_smax(t["s_max_mm"], t["i_m"], 8.0) == pytest.approx(1.0)


def test_trough_integrates_to_the_lost_volume():
    t = trough(20.0, 8.0, 1.0, 0.5); s = t["s_max_mm"] / 1000; i = t["i_m"]
    ys = [-6 * i + 12 * i * j / 4000 for j in range(4001)]
    area = sum(transverse(y, 20.0, i, s)[0] for y in ys) * (ys[1] - ys[0])
    assert area == pytest.approx(t["lost_volume_m3_per_m"], rel=1e-3)


def test_slope_and_strain_extremes():
    z0, i, s = 20.0, 10.0, 0.02
    slopes = [abs(transverse(y, z0, i, s)[2]) for y in (5.0, 9.9, 10.0, 10.1, 15.0)]
    assert max(slopes) == slopes[2]                              # inflection at y = i
    assert transverse(0.0, z0, i, s)[3] == pytest.approx(s / z0)  # compression under the axis
    assert transverse(math.sqrt(3) * i, z0, i, s)[3] == pytest.approx(-2 * s * math.exp(-1.5) / z0)  # max tension


def test_longitudinal_profile():
    assert longitudinal(0.0, 10.0, 0.02) == pytest.approx(0.01)   # half the final settlement at the face
    assert longitudinal(-40.0, 10.0, 0.02) == pytest.approx(0.02, rel=1e-3)
    assert longitudinal(40.0, 10.0, 0.02) < 1e-6
    pr = profiles(20.0, 10.0, 0.02, 21)
    assert len(pr["y_m"]) == 21 and max(pr["s_mm"]) == pytest.approx(20.0)


def test_damage_categories():
    assert damage_category(5.0, 1 / 1000)[0] == 1
    assert damage_category(30.0, 1 / 1000)[0] == 2      # settlement governs
    assert damage_category(5.0, 1 / 300)[0] == 2        # slope governs
    assert damage_category(60.0, 1 / 100)[0] == 3
    assert damage_category(100.0, 1 / 20)[0] == 4


def test_k_and_volume_loss_estimates():
    clay = GroundZone(ch_from=0, ch_to=100, ground_kind="soil", fines_pct=60)
    sand = GroundZone(ch_from=0, ch_to=100, ground_kind="soil", fines_pct=5)
    rock = GroundZone(ch_from=0, ch_to=100, ground_kind="rock")
    assert (trough_k(clay), trough_k(sand), trough_k(rock)) == (0.5, 0.3, 0.25)
    assert estimate_volume_loss(clay, "epb")[0] == 1.0
    assert estimate_volume_loss(sand, "epb")[0] == 0.5
    assert estimate_volume_loss(sand, "epb", "Ka")[0] == 0.75
    assert estimate_volume_loss(sand, "gripper")[0] == 1.0        # no face support in soil
    assert estimate_volume_loss(rock, "gripper")[0] == 0.1
    z = GroundZone(ch_from=0, ch_to=100, ground_kind="soil", fines_pct=5, volume_loss_pct=0.3, trough_k=0.45)
    assert estimate_volume_loss(z, "epb") == (0.3, "zone input") and trough_k(z) == 0.45


def test_route_screening_metro():
    p = example_project("metro")
    rt = assess_route(p)
    st = rt["settlement"]
    assert st["worst_zone"] == "Silty sand" and 25 < st["s_max_mm"] < 40
    assert all("settlement" in z for z in rt["zones"])
    assert any("settlement assessment is needed" in w for w in rt["warnings"])
    # project-wide V_L overrides the estimate; a zone value overrides both
    p2 = p.model_copy(deep=True); p2.settlement.volume_loss_pct = 0.2
    z = next(z for z in p2.route.zones if z.name == "Silty sand")
    s2 = zone_settlement(p2, z)
    assert s2["basis"] == "project input" and s2["s_max_mm"] == pytest.approx(st["s_max_mm"] * 0.2 / 0.75)
    z.volume_loss_pct = 0.1
    assert zone_settlement(p2, z)["basis"] == "zone input"


def test_settlement_figure_and_api():
    pytest.importorskip("matplotlib")
    from fastapi.testclient import TestClient
    from tunco2pro import figures as F
    from tunco2pro.api import app
    p = example_project("metro")
    fig, d = F.make_settlement(p)
    F.to_bytes(fig, "pdf")
    assert d["zone"] == "Silty sand" and len(d["zones"]) == len(p.route.zones)
    c = TestClient(app)
    r = c.post("/api/settlement/trough", json={"axis_depth_m": 20, "tbm_diameter_m": 8, "volume_loss_pct": 1.0, "trough_k": 0.5})
    assert r.status_code == 200 and r.json()["s_max_mm"] == pytest.approx(20.05, abs=0.01)
    r = c.post("/api/settlement", json={"project": p.model_dump(mode="json")})
    assert r.status_code == 200 and r.json()["zones"][0]["profiles"]["s_mm"]
