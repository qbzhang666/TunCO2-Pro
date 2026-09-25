import math
import trimesh
from fastapi.testclient import TestClient
from tunco2pro.api import app
from tunco2pro.geometry import build_rings
from tunco2pro.models import Geometry
from tunco2pro.optimise import OptimiseInput, optimise

client = TestClient(app)


def test_segments_watertight_and_volume():
    g = Geometry(); segs = build_rings(g, n_rings=2)
    assert len(segs) == 2 * g.segments_per_ring
    for s in segs:
        m = trimesh.Trimesh(s.vertices, s.faces)
        assert m.is_watertight and m.is_winding_consistent and m.volume > 0
    A = math.pi / 4 * ((g.inner_diameter_m + 2 * g.lining_thickness_m) ** 2 - g.inner_diameter_m ** 2)
    expected = A * 2 * (g.ring_width_m - 0.01) * (1 - g.segments_per_ring * 0.4 / 360)
    assert abs(sum(s.volume_m3 for s in segs) / expected - 1) < 0.005


def test_api_endpoints():
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.post("/api/assess", json={}); assert r.status_code == 200 and r.json()["total_tCO2e"] > 0
    assert client.post("/api/report.xlsx", json={}).content[:2] == b"PK"
    assert client.post("/api/geometry?fmt=glb&rings=2", json={}).content[:4] == b"glTF"
    import importlib.util as u
    r = client.post("/api/geometry?fmt=ifc&rings=1", json={})
    assert (b"IFC4X3" in r.content[:2000]) if u.find_spec("ifcopenshell") else r.status_code == 501
    r = client.post("/api/geometry?fmt=3dm&rings=1", json={})
    assert r.status_code == (200 if u.find_spec("rhino3dm") else 501)
    assert client.get("/").status_code == 200


def test_optimiser_respects_fos_constraint():
    o = optimise(OptimiseInput(pop_size=24, n_gen=10, fos_min=2.0))
    assert o["feasible"] and all(s["fos"] >= 2.0 - 1e-9 for s in o["pareto"])
    assert min(s["carbon_kg_per_m"] for s in o["pareto"]) < o["baseline_carbon_kg_per_m"]
