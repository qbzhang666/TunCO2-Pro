"""Six TBM types and the GIS > BIM corridor bridge."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from tunco2pro import gisbim
from tunco2pro.api import app
from tunco2pro.carbon import assess
from tunco2pro.models import ProjectInput, Route
from tunco2pro.tbm_types import ORDER, applicability, compare

client = TestClient(app)


def test_geodesy_matches_reference_utm():
    """Reference values from PROJ (EPSG:4326 -> EPSG:32754)."""
    for (lon, lat), (e0, n0) in {(141.0, -34.0): (500000.0, 6237844.0224), (142.123456, -35.5): (601891.8517, 6070926.4078),
                                 (139.5, -33.2): (360186.8005, 6325538.4191)}.items():
        e, n = gisbim.lonlat_to_grid(lon, lat, 32754)
        assert e == pytest.approx(e0, abs=0.002) and n == pytest.approx(n0, abs=0.002)
        lo, la = gisbim.grid_to_lonlat(e0, n0, 32754)
        assert lo == pytest.approx(lon, abs=1e-8) and la == pytest.approx(lat, abs=1e-8)


def test_applicability_follows_classification_chart():
    rock = applicability("rock", "competent")
    assert rock["gripper"]["rating"] == "suitable" and rock["epb"]["rating"] == "marginal"
    assert applicability("rock", "weak")["gripper"]["rating"] == "unsuitable"
    soil_fine = applicability("soil", k_m_s=1e-8)
    assert soil_fine["epb"]["rating"] == "suitable" and soil_fine["slurry"]["rating"] == "marginal"
    soil_coarse = applicability("soil", k_m_s=1e-2)
    assert soil_coarse["slurry"]["rating"] == "suitable" and soil_coarse["epb"]["rating"] == "marginal"
    overlap = applicability("soil", k_m_s=1e-4)
    assert overlap["epb"]["rating"] == overlap["slurry"]["rating"] == "suitable"
    for t in ("gripper", "single_shield", "double_shield"):
        assert applicability("soil", k_m_s=1e-4)[t]["rating"] == "unsuitable"
    assert applicability("mixed", k_m_s=1e-5)["multi_mode"]["rating"] == "suitable"


def test_machine_type_drives_models():
    p = ProjectInput()
    p.tbm.machine_type = "slurry"
    p.tbm.separation_kwh_per_m3 = 5
    r = assess(p)
    assert r.intermediate["tbm_mass_model"] == "Slurry"
    assert any(i.element == "Slurry circuit (user)" for i in r.items)
    p.tbm.machine_type = "gripper"
    assert any("EPB regression used" in w for w in assess(p).warnings)


def test_compare_six_types():
    c = compare(ProjectInput(route=Route()))
    assert [t["type"] for t in c["types"]] == ORDER
    mm = next(t for t in c["types"] if t["type"] == "multi_mode")
    epb = next(t for t in c["types"] if t["type"] == "epb")
    assert mm["thrust_MN"] >= epb["thrust_MN"] and mm["mass_t"] >= epb["mass_t"]


@pytest.mark.parametrize("key", ["metro", "railway", "road", "hydro"])
def test_example_corridors_register_and_zone(key):
    r = gisbim.example_route(key)
    reg = r.source["registration"]
    assert reg["s0_m"] == pytest.approx(300.0, abs=2.0) and reg["rms_m"] < 0.2   # examples are generated with s0 = 300 m
    assert r.crs.epsg == 32754
    assert r.zones[0].ch_from == pytest.approx(r.alignment.start_chainage_m)
    assert r.zones[-1].ch_to == pytest.approx(r.alignment.end_chainage_m)
    assert len(r.zones) >= 2 and all(z.cover_m > 0 for z in r.zones)
    if key == "metro":
        assert {"soil", "mixed"} & {z.ground_kind for z in r.zones}
    if key == "hydro":
        assert any(z.unit == "FZ" for z in r.zones) and max(z.cover_m for z in r.zones) > 300


def _example_project(key="metro", machine="epb"):
    d = client.post(f"/api/gis/example/{key}").json()
    proj = ProjectInput().model_dump()
    proj["geometry"].update(d["suggested_geometry"]); proj["functional"].update(d["suggested_functional"])
    proj["route"] = d["route"]; proj["tunnel_length_m"] = d["length_m"]; proj["tbm"]["machine_type"] = machine
    return d, proj


def test_gis_endpoints_and_georeferenced_exports():
    d, proj = _example_project()
    assert set(client.get("/api/gis/examples").json()) == {"metro", "railway", "road", "hydro"}
    assert client.get("/api/gis/examples/road/plan_line.csv").text.startswith("chainage_m,easting,northing,ground_m")
    gj = client.post("/api/gis/geojson", json={"project": proj}).json()
    lon, lat, _ = gj["features"][0]["geometry"]["coordinates"][0]
    assert 140 < lon < 142 and -35 < lat < -33
    z = zipfile.ZipFile(io.BytesIO(client.post("/api/gis/blender", json={"project": proj}).content))
    names = set(z.namelist())
    assert {"tunco2pro_scene.json", "tunco2pro_route.glb", "epb.glb", "tunco2_to_blender.py"} <= names
    sc = json.loads(z.read("tunco2pro_scene.json"))
    assert sc["frame"]["crs"]["epsg"] == 32754 and len(sc["zones"]) == len(d["route"]["zones"])
    assert client.post("/api/gis/geojson", json={"project": ProjectInput(route=Route()).model_dump()}).status_code == 422


def test_ifc_is_in_metres_and_georeferenced():
    ifc = pytest.importorskip("ifcopenshell")
    d, proj = _example_project("road")
    r = client.post("/api/geometry?fmt=ifc&lod=200&max_rings=20", json={"project": proj})
    assert r.status_code == 200
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
        f.write(r.content)
    m = ifc.open(f.name)
    assert [u.Prefix for u in m.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT"] == [None]
    mc = m.by_type("IfcMapConversion")[0]
    o = json.loads(client.get("/api/gis/examples/road/crs.json").text)["origin"]
    assert (mc.Eastings, mc.Northings, mc.OrthogonalHeight) == (o["easting"], o["northing"], o["height"])
    assert m.by_type("IfcProjectedCRS")[0].Name == "EPSG:32754"


def test_tbm_catalogue_and_models():
    d = client.get("/api/tbm/types").json()
    assert [t["key"] for t in d["types"]] == ORDER
    for k in ORDER:
        assert client.get(f"/static/assets/tbm/{k}.glb").status_code == 200


def test_gui_support_endpoints():
    d = client.get("/api/defaults").json()
    assert d["field_help"]["geometry.tbm_diameter_m"]["min_excl"] == 0
    p = client.post("/api/route/plan", json={"project": ProjectInput(route=Route()).model_dump()}).json()
    assert not p["georeferenced"] and len(p["zones"]) == 3
    _, proj = _example_project("hydro")
    g = client.post("/api/route/plan", json={"project": proj}).json()
    lat, lon = g["zones"][0]["latlng"][0]
    assert g["georeferenced"] and -35 < lat < -33 and 140 < lon < 142
    for f in ("/", "/static/app.js", "/static/viewer.js", "/static/vendor/leaflet/leaflet.js"):
        assert client.get(f).status_code == 200


def test_example_comparison_design():
    """Metro/Road isolate size (EPB 7.25 vs 15.6 m); Metro/Railway isolate the machine (EPB vs slurry, 7.25 m);
    Hydro is a 10.45 m single shield. Each machine must suit most of its own route."""
    c = gisbim.compare_examples()
    r = {x["key"]: x for x in c["examples"]}
    assert (r["metro"]["machine"], r["metro"]["tbm_diameter_m"]) == ("epb", 7.25)
    assert (r["road"]["machine"], r["road"]["tbm_diameter_m"]) == ("epb", 15.6)
    assert (r["railway"]["machine"], r["railway"]["tbm_diameter_m"]) == ("slurry", 7.25)
    assert (r["hydro"]["machine"], r["hydro"]["tbm_diameter_m"]) == ("single_shield", 10.45)
    assert r["hydro"]["reference"] and "106404" in r["hydro"]["reference"]
    for x in r.values():
        assert x["machine_suitable_share"] >= 0.75, x["key"]
        assert x["kgCO2e_per_m"] == pytest.approx(sum(x["modules_kgCO2e_per_m"].values()), rel=1e-6)
    assert r["road"]["kgCO2e_per_m"] > 3 * r["metro"]["kgCO2e_per_m"]          # ~ D^2
    assert r["road"]["tCO2e_per_functional_unit"] == pytest.approx(r["road"]["kgCO2e_per_m"] / 3)
    assert client.get("/api/gis/examples/compare").status_code == 200


def test_slurry_circuit_energy():
    from tunco2pro.slurry import SlurryCircuit, estimate
    s = SlurryCircuit()
    e = estimate(s, 7.25, 4800, 50)
    # Cv = (1.3-1.1)/(2.65-1.1); slurry volume = (1-0.35)/Cv
    assert e["cv"] == pytest.approx(0.2 / 1.55) and e["slurry_m3_per_m3"] == pytest.approx(0.65 / (0.2 / 1.55))
    assert 1 < e["velocity_m_s"] < 5 and 1 < e["kwh_per_m3"] < 10
    assert estimate(s, 7.25, 9600, 50)["pumping_kwh_per_m3"] > e["pumping_kwh_per_m3"]   # longer line, more friction
    p = gisbim.example_project("railway")
    items = {i.element: i.kg_per_m for i in assess(p.model_copy(update={"route": None})).items}
    assert items["Slurry pumping"] > 0 and items["Slurry separation plant"] > 0
    p.tbm.slurry.mode = "user"; p.tbm.slurry.user_kwh_per_m3 = 5
    items = {i.element: i.kg_per_m for i in assess(p.model_copy(update={"route": None})).items}
    assert items["Slurry circuit (user)"] == pytest.approx(5 * 3.14159265 / 4 * 7.25 ** 2 * 0.85, rel=1e-4)
    p.tbm.machine_type = "epb"
    assert not any("Slurry" in k for k in {i.element for i in assess(p.model_copy(update={"route": None})).items})


def test_selection_by_fines_content():
    """DAUB 2025: EPB needs >= 15 % fines; slurry is limited above ~40 % (separation)."""
    a = applicability("soil", k_m_s=1e-5, fines_pct=8)
    assert a["epb"]["rating"] == "marginal" and a["slurry"]["rating"] == "suitable"
    b = applicability("soil", k_m_s=1e-5, fines_pct=45)
    assert b["epb"]["rating"] == "suitable" and b["slurry"]["rating"] == "marginal"
    assert applicability("soil", k_m_s=1e-3)["epb"]["rating"] == "marginal"         # above the conditioned range
    assert applicability("soil", k_m_s=1e-7)["slurry"]["rating"] == "marginal"


def test_jsce_control_pressure():
    """p = K0 sigma'_v + u_w + dp with K0 = 1 - sin(phi) (Jaky); bound = total vertical stress at the crown."""
    import math
    from tunco2pro.alignment import GroundZone
    from tunco2pro.face import FaceSupport, zone_support
    z = GroundZone(ch_from=0, ch_to=100, cover_m=20, unit_weight_kn_m3=20, friction_deg=30, water_head_m=16)
    s = zone_support(z, 7.0, FaceSupport())
    u = 9.81 * 16
    assert s["p_control_axis_kpa"] == pytest.approx((1 - math.sin(math.radians(30))) * (400 - u) + u + 20)
    assert s["upper_crown_kpa"] == pytest.approx(20 * 16.5) and s["within_band"]
    ka = zone_support(z, 7.0, FaceSupport(earth_coefficient="Ka"))
    assert ka["p_control_axis_kpa"] < s["p_control_axis_kpa"]


def test_regression_pressure_models():
    from tunco2pro import tbm
    from tunco2pro.models import TBMLoads
    D = 7.25
    L = TBMLoads(thrust_model="regression_pressure", torque_model="regression_pressure", tbm_type_thrust="EPB TBM", tbm_type_torque="EPB TBM")
    assert tbm.torque_mnm(L, D) == pytest.approx(tbm.TORQUE_BY_TYPE["EPB TBM"](D))     # reference condition
    hi = L.model_copy(update={"support_pressure_kpa": tbm.reference_pressure_kpa(D) + 100})
    assert tbm.thrust_mn(hi, D) - tbm.thrust_mn(L, D) == pytest.approx(3.14159265 / 4 * D ** 2 * 0.1, rel=1e-6)
    slurry = hi.model_copy(update={"f": 0.05})
    assert tbm.torque_mnm(hi, D) - tbm.torque_mnm(L, D) > 4 * (tbm.torque_mnm(slurry, D) - tbm.torque_mnm(L, D)) > 0


def test_xie2024_thrust_reproduces_published_drives():
    """Xie et al. (2024): 6.98 m EPB (510 t, L 9.0 m) in clay recorded 10-20 MN; 12.0 m Mixshield (1274 t, L 14.88 m)
    in sand with confined water recorded 40-100 MN."""
    from tunco2pro.models import TBMLoads
    from tunco2pro.tbm import tbm_mass_kg, xie2024_thrust_mn
    for z0 in (12.2, 27):
        up, lo = xie2024_thrust_mn(TBMLoads(H=z0, gamma=19.9, K0=0.43, c=30, H_w=0, permeability_m_s=4.8e-9,
                                            shield_length_m=9.0, shield_friction=0.2), 6.98, 510)
        assert 7 < lo < up < 23
    for z0 in (15, 37.5):
        up, lo = xie2024_thrust_mn(TBMLoads(H=z0, gamma=18.9, K0=0.36, c=5, H_w=z0 - 1, permeability_m_s=1e-4,
                                            shield_length_m=14.88, shield_friction=0.3), 12.0, 1274)
        assert 35 < lo < up < 100
    # F5: the mass regressions are in tonnes (510 t EPB at 6.98 m)
    from tunco2pro.models import TBM
    assert tbm_mass_kg(TBM(mass_model="EPB"), 6.98) / 1000 == pytest.approx(510, rel=0.02)


def test_api_example_route_keeps_groundwater():
    """The route returned for the GUI must carry the example's water table, as the project does."""
    from fastapi.testclient import TestClient
    from tunco2pro.api import app
    d = TestClient(app).post("/api/gis/example/metro").json()
    assert all(z["water_head_m"] is not None for z in d["route"]["zones"])
    assert d["route"]["zones"][0]["water_head_m"] == d["project"]["route"]["zones"][0]["water_head_m"]
