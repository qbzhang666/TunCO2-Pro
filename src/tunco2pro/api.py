"""FastAPI service: JSON API + the browser front end (served from /)."""
from __future__ import annotations

import html as html_mod
import os
import re as re_mod
import tempfile
from importlib import resources
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .carbon import assess, strategies
from .ccm import Ground, Support, curves
from .factors import load_library
from .alignment import default_zones, from_landxml, straight_with_curve
from .geometry import LOD_CONTENT, elements_to_3dm, elements_to_glb, elements_to_ifc, route_elements
from .models import ProjectInput, Route
from .optimise import OptimiseInput, ParametricInput, optimise, parametric
from .route import assess_route, optimise_route
from .report import build_workbook
from . import gisbim, tbm_types

app = FastAPI(title="TunCO2 Pro", version=__version__,
              description="Embodied carbon (EN 15978 A1-A5) and low-carbon lining design for TBM tunnels. "
                          "Open source (MIT licence).")
WEB = Path(str(resources.files("tunco2pro") / "web"))


class AssessRequest(BaseModel):
    project: ProjectInput = ProjectInput()
    compat_v1: bool = False


class StabilityRequest(BaseModel):
    ground: Ground = Ground()
    support: Support = Support()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "factor_library": load_library().version}


def _project(req: "AssessRequest") -> ProjectInput:
    """v1 compatibility implies the v1 factor set."""
    return req.project.model_copy(update={"factor_set": "v1"}) if req.compat_v1 else req.project


def _field_help(model, prefix="") -> dict:
    """path -> {description, bounds} for GUI tooltips and validation, from the pydantic models."""
    import annotated_types as at
    out = {}
    for name, f in model.model_fields.items():
        path = f"{prefix}{name}"
        ann = f.annotation
        sub = getattr(ann, "model_fields", None) and ann
        if sub:
            out.update(_field_help(sub, path + "."))
            continue
        h = {}
        if f.description:
            h["description"] = f.description
        for m in f.metadata:
            if isinstance(m, at.Ge): h["min"] = m.ge
            if isinstance(m, at.Gt): h["min_excl"] = m.gt
            if isinstance(m, at.Le): h["max"] = m.le
            if isinstance(m, at.Lt): h["max_excl"] = m.lt
        if h:
            out[path] = h
    return out


@app.get("/api/defaults")
def defaults():
    return {"project": ProjectInput().model_dump(), "ground": Ground().model_dump(),
            "optimise": OptimiseInput().model_dump(exclude={"project"}),
            "route": Route().model_dump(), "lod_content": LOD_CONTENT,
            "parametric": ParametricInput().model_dump(exclude={"project"}),
            "field_help": _field_help(ProjectInput)}


@app.post("/api/route/plan")
def api_route_plan(req: AssessRequest):
    """Zone polylines for the map: lon/lat when the route is georeferenced, else local x/y (no assessment)."""
    p = _project(req)
    route = p.route or Route()
    al = route.alignment
    geo = route.crs is not None
    def pt(q):
        if geo:
            lon, lat = gisbim.local_to_lonlat(q[0], q[1], route.crs)
            return [round(lat, 7), round(lon, 7)]
        return [round(q[1], 2), round(q[0], 2)]
    zones = [{"index": i, "name": z.name, "ch_from": z.ch_from, "ch_to": z.ch_to, "ground_kind": z.ground_kind,
              "unit": z.unit, "latlng": [pt(q) for q in gisbim._zone_polyline(al, z.ch_from, z.ch_to)]}
             for i, z in enumerate(route.zones)]
    return {"georeferenced": geo, "crs": route.crs.model_dump() if geo else None, "name": al.name,
            "start_chainage_m": al.start_chainage_m, "end_chainage_m": al.end_chainage_m, "zones": zones}


@app.get("/api/factors")
def factors(factor_set: str = Query("current", pattern="^(current|v1)$")):
    lib = load_library(factor_set)
    return {"version": lib.version, "factor_set": factor_set, "factors": [f.__dict__ for f in lib.all()],
            "concrete_locations": sorted({r["Location"] for r in lib.concrete_db}),
            "concrete_types": sorted({r["Type"] for r in lib.concrete_db})}


@app.post("/api/assess")
def api_assess(req: AssessRequest):
    try:
        p = _project(req)
        res = assess(p, compat_v1=req.compat_v1)
        out = res.to_dict()
        out["strategies"] = strategies(p, res, compat_v1=req.compat_v1)
        return out
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/report.xlsx")
def api_report(req: AssessRequest):
    p = _project(req)
    lib = load_library(p.factor_set).with_overrides(p.factor_overrides)
    res = assess(p, compat_v1=req.compat_v1)
    rt = assess_route(p, compat_v1=req.compat_v1) if p.route else None
    data = build_workbook(p, res, lib, strategies(p, res, compat_v1=req.compat_v1), rt)
    fn = "".join(c if c.isalnum() else "_" for c in p.name)[:40] or "report"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="TunCO2Pro_{fn}.xlsx"'})


@app.post("/api/stability")
def api_stability(req: StabilityRequest):
    return curves(req.ground, req.support)


class TroughRequest(BaseModel):
    axis_depth_m: float = Field(..., gt=0, description="Axis depth z0")
    tbm_diameter_m: float = Field(..., gt=0)
    volume_loss_pct: float = Field(1.0, ge=0, le=20)
    trough_k: float = Field(0.5, gt=0, lt=1.5)
    n: int = Field(61, ge=5, le=1001)


@app.post("/api/settlement/trough")
def api_trough(req: TroughRequest):
    """Gaussian trough for one section: i, S_max, slope, strains, Rankin category and the sampled profiles."""
    from .settlement import damage_category, profiles, trough
    t = trough(req.axis_depth_m, req.tbm_diameter_m, req.volume_loss_pct, req.trough_k)
    cat, text = damage_category(t["s_max_mm"], t["slope_max"])
    return {**t, "damage_category": cat, "damage_text": text, "profiles": profiles(req.axis_depth_m, t["i_m"], t["s_max_mm"] / 1000, req.n)}


@app.post("/api/settlement")
def api_settlement(req: AssessRequest):
    """Volume-loss settlement screening of every ground zone of the route, with profiles."""
    from .settlement import zone_settlement
    p = _project(req)
    if not p.route or not p.route.zones:
        raise HTTPException(422, "the project has no route with ground zones")
    return {"zones": [{"zone": z.name, "ch_from": z.ch_from, "ch_to": z.ch_to, "cover_m": z.cover_m, "ground_kind": z.ground_kind,
                       **zone_settlement(p, z, with_profiles=True)} for z in sorted(p.route.zones, key=lambda z: z.ch_from)],
            "criteria": p.settlement.model_dump()}


@app.post("/api/optimise")
def api_optimise(req: OptimiseInput):
    return optimise(req)


@app.post("/api/geometry")
def api_geometry(req: AssessRequest, fmt: str = Query("glb", pattern="^(glb|ifc|3dm)$"),
                 rings: int = Query(8, ge=1, le=400), lod: int | None = Query(None),
                 max_rings: int = Query(240, ge=10, le=2000)):
    if fmt == "ifc":
        max_rings = min(max_rings, 120)  # keep IFC files manageable (~10 MB)
    """Model along the route (or a short straight stretch of `rings` rings) at the chosen LoD."""
    p = _project(req)
    lod = lod or p.lod
    if lod not in LOD_CONTENT:
        raise HTTPException(422, "lod must be 100, 200, 300, 400 or 500")
    if p.route is None:
        L = rings * p.geometry.ring_width_m
        p = p.model_copy(update={"route": Route(alignment=straight_with_curve(L, None, -25, -25, step=L),
                                                zones=[default_zones(L)[0].model_copy(update={"ch_from": 0, "ch_to": L, "name": "Section"})])})
    res = assess(p.model_copy(update={"route": None}), compat_v1=req.compat_v1)
    it = {i.element: i.kg_per_m for i in res.items}; im = res.intermediate
    per_m3 = {"lining": (it.get("Lining concrete", 0) + it.get("Lining reinforcement", 0)) / im["ring_area_m2"],
              "grout": it.get("Annulus grout", 0) / im["grout_area_m2"] if im["grout_area_m2"] else 0,
              "invert": it.get("Invert backfill", 0) / im["invert_area_m2"] if im["invert_area_m2"] else 0}
    els, meta = route_elements(p, lod, max_rings=max_rings, per_m3=per_m3)
    if fmt == "glb":
        al = p.route.alignment
        P, T, _, _ = al.frame(al.end_chainage_m)
        return Response(elements_to_glb(els), media_type="model/gltf-binary",
                        headers={"X-TunCO2-Elements": str(len(els)), "X-TunCO2-Note": meta["note"],
                                 "X-TunCO2-Face": ",".join(f"{v:.3f}" for v in [*P, *T]),
                                 "Access-Control-Expose-Headers": "X-TunCO2-Face"})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + fmt); tmp.close()
    try:
        if fmt == "ifc":
            elements_to_ifc(els, tmp.name, p.name, meta, {"name": p.route.alignment.name, "length_m": p.route.alignment.length_m,
                                                          "crs": p.route.crs.model_dump() if p.route.crs else None})
            mt = "application/x-step"
        else:
            elements_to_3dm(els, tmp.name); mt = "application/octet-stream"
    except ModuleNotFoundError as e:
        extra = "ifc" if fmt == "ifc" else "rhino"
        raise HTTPException(501, f"{e.name} not installed: pip install 'tunco2pro[{extra}]'")
    return FileResponse(tmp.name, media_type=mt, filename=f"TunCO2Pro_LoD{lod}.{fmt}")


@app.post("/api/route")
def api_route(req: AssessRequest):
    p = _project(req)
    if p.route is None:
        p = p.model_copy(update={"route": Route()})
    try:
        return assess_route(p, compat_v1=req.compat_v1)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


class RouteOptRequest(BaseModel):
    project: ProjectInput
    algorithm: str = "nsga2"
    discrete_grades: bool = True
    pop_size: int = 40
    n_gen: int = 30


@app.post("/api/route/optimise")
def api_route_optimise(req: RouteOptRequest):
    p = req.project if req.project.route else req.project.model_copy(update={"route": Route()})
    return optimise_route(p, req.algorithm, req.pop_size, req.n_gen, req.discrete_grades)


@app.post("/api/parametric")
def api_parametric(req: ParametricInput):
    return parametric(req)


@app.post("/api/alignment/landxml")
def api_landxml(xml: str = Body(..., media_type="application/xml"), depth_m: float = Query(-25.0)):
    try:
        al = from_landxml(xml, depth_m)
    except Exception as e:  # noqa: BLE001 - report parse problems to the user
        raise HTTPException(422, f"Could not read LandXML: {e}")
    return {"alignment": al.model_dump(), "length_m": al.length_m, "zones": [z.model_dump() for z in default_zones(al.length_m, al.start_chainage_m)]}


@app.post("/api/alignment/simple")
def api_simple_alignment(length_m: float = Query(1000, gt=0), radius_m: float | None = Query(None),
                         depth_start: float = Query(-25), depth_end: float = Query(-30)):
    al = straight_with_curve(length_m, radius_m, depth_start, depth_end)
    return {"alignment": al.model_dump(), "length_m": al.length_m}


# ------------------------------------------------------------------ cutterhead mechanics
@app.get("/api/cutterhead/ranges")
def api_cutterhead_ranges():
    from . import cutterhead
    return {"ranges": cutterhead.range_table(), "doc": "docs/CUTTERHEAD.md"}


# ------------------------------------------------------------------ TBM types
@app.get("/api/tbm/types")
def api_tbm_types():
    meta = WEB / "assets" / "tbm" / "tbm_models.json"
    models = __import__("json").loads(meta.read_text()) if meta.exists() else {}
    return {"types": tbm_types.catalogue(), "models": models,
            "model_note": "Generic representation of each machine type, drawn on a common shield envelope and "
                          "scaled to the project TBM diameter (for visualisation, not a design)."}


@app.post("/api/tbm/compare")
def api_tbm_compare(req: AssessRequest):
    try:
        return tbm_types.compare(_project(req), compat_v1=req.compat_v1)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


# ------------------------------------------------------------------ GIS > BIM
class CorridorImport(BaseModel):
    plan_csv: str
    long_section: dict | str
    crs: dict
    tbm_diameter_m: float = 7.0
    ch_from: float | None = None
    ch_to: float | None = None
    min_zone_m: float = 40.0
    step_m: float = 5.0
    groundwater_depth_m: float | None = None
    units_csv: str | None = None
    track: str = "alignment"
    name: str = "Corridor"


def _route_payload(route: Route) -> dict:
    return {"route": route.model_dump(), "length_m": route.alignment.length_m, "source": route.source}


@app.get("/api/gis/examples")
def api_gis_examples():
    """The bundled synthetic corridors (Metro, Railway, Road, Hydro tunnels)."""
    return {k: {"name": v["name"], "summary": v["summary"], "geometry": v["geometry"], "functional": v["functional"],
                "machine": v["machine"], "reference": v.get("reference")}
            for k, v in gisbim.EXAMPLES.items()}


@app.get("/api/gis/examples/compare")
def api_gis_examples_compare(compat_v1: bool = Query(False)):
    """The four examples assessed on one basis, normalised per metre, per m3 excavated and per track/lane-km."""
    return gisbim.compare_examples(compat_v1)


@app.get("/api/gis/examples/{key}/{fname}")
def api_gis_example_file(key: str, fname: str):
    """Download an example's input files, to see the import formats."""
    if key not in gisbim.EXAMPLES or fname not in ("plan_line.csv", "long_section.json", "crs.json"):
        raise HTTPException(404, "unknown example file")
    plan, ls, crs = gisbim.example_files(key)
    body = {"plan_line.csv": plan, "long_section.json": ls, "crs.json": __import__("json").dumps(crs, indent=1)}[fname]
    return Response(body, media_type="text/csv" if fname.endswith(".csv") else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="{key}_{fname}"'})


@app.post("/api/gis/example/{key}")
def api_gis_example(key: str, tbm_diameter_m: float | None = Query(None, gt=0), min_zone_m: float = Query(40.0, ge=0),
                    groundwater_depth_m: float | None = Query(None, ge=0)):
    try:
        # the example's own groundwater depth unless the user gives one (passing None would remove the water)
        r = gisbim.example_route(key, tbm_diameter_m, min_zone_m=min_zone_m,
                                 **({"groundwater_depth_m": groundwater_depth_m} if groundwater_depth_m is not None else {}))
    except ValueError as e:
        raise HTTPException(404, str(e))
    ex = gisbim.EXAMPLES[key]
    out = _route_payload(r)
    out["suggested_geometry"] = {**ex["geometry"], **({"tbm_diameter_m": tbm_diameter_m} if tbm_diameter_m else {})}
    out["suggested_functional"] = ex["functional"]
    out["suggested_name"] = ex["name"]
    proj = gisbim.example_project(key, tbm_diameter_m=tbm_diameter_m, min_zone_m=min_zone_m,
                                  **({"groundwater_depth_m": groundwater_depth_m} if groundwater_depth_m is not None else {}))
    out["project"] = proj.model_dump()
    out["reference"] = ex.get("reference")
    out["suggested_length_m"] = r.alignment.length_m
    return out


@app.post("/api/gis/import")
def api_gis_import(req: CorridorImport):
    try:
        plan = gisbim.read_plan_csv(req.plan_csv)
        st = gisbim.read_long_section(req.long_section, req.track)
        crs = gisbim.crs_from_json(req.crs)
        units = gisbim.load_units(req.units_csv) if req.units_csv else None
        r = gisbim.corridor_route(plan, st, crs, req.tbm_diameter_m, ch_from=req.ch_from, ch_to=req.ch_to,
                                  step_m=req.step_m, min_zone_m=req.min_zone_m, units=units,
                                  groundwater_depth_m=req.groundwater_depth_m, name=req.name)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"Could not build the route: {e}")
    return _route_payload(r)


def _georef_project(req: AssessRequest) -> ProjectInput:
    p = _project(req)
    if p.route is None or p.route.crs is None:
        raise HTTPException(422, "The route is not georeferenced: import a corridor (GIS) first.")
    return p


@app.post("/api/gis/geojson")
def api_gis_geojson(req: AssessRequest):
    p = _georef_project(req)
    rt = assess_route(p, compat_v1=req.compat_v1)
    gj = gisbim.route_geojson(p.route, rt, rt["tbm_applicability"])
    return Response(__import__("json").dumps(gj), media_type="application/geo+json",
                    headers={"Content-Disposition": 'attachment; filename="tunco2pro_route.geojson"'})


@app.post("/api/gis/blender")
def api_gis_blender(req: AssessRequest, lod: int = Query(300), max_rings: int = Query(240, ge=10, le=2000)):
    """Zip for the Blender importer: scene JSON, route glTF, TBM glTF, GeoJSON and the importer script."""
    import io
    import json
    import zipfile
    p = _georef_project(req)
    rt = assess_route(p, compat_v1=req.compat_v1)
    tt = p.tbm.machine_type
    scene = gisbim.blender_scene(p.route, rt, rt["tbm_applicability"], tbm_type=tt,
                                 tbm_diameter_m=p.geometry.tbm_diameter_m, project_name=p.name)
    res = assess(p.model_copy(update={"route": None}), compat_v1=req.compat_v1)
    it = {i.element: i.kg_per_m for i in res.items}; im = res.intermediate
    per_m3 = {"lining": (it.get("Lining concrete", 0) + it.get("Lining reinforcement", 0)) / im["ring_area_m2"],
              "grout": it.get("Annulus grout", 0) / im["grout_area_m2"] if im["grout_area_m2"] else 0,
              "invert": it.get("Invert backfill", 0) / im["invert_area_m2"] if im["invert_area_m2"] else 0}
    els, meta = route_elements(p, lod, max_rings=max_rings, per_m3=per_m3)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("tunco2pro_scene.json", json.dumps(scene, indent=1))
        z.writestr("tunco2pro_route.glb", elements_to_glb(els))
        z.writestr("tunco2pro_route.geojson", json.dumps(gisbim.route_geojson(p.route, rt, rt["tbm_applicability"])))
        if tt and (WEB / "assets" / "tbm" / f"{tt}.glb").exists():
            z.write(WEB / "assets" / "tbm" / f"{tt}.glb", f"{tt}.glb")
        script = resources.files("tunco2pro") / "integrations" / "tunco2_to_blender.py"
        if script.is_file():
            z.writestr("tunco2_to_blender.py", script.read_text(encoding="utf-8"))
        z.writestr("README.txt", "Open Blender (4.2+), Scripting tab, open tunco2_to_blender.py and Run Script,\n"
                   "or: blender --python tunco2_to_blender.py -- <this folder>\n"
                   "Coordinates are local metres about the project origin in the CRS file; any Blender scene or IFC\n"
                   "model that uses the same origin overlays this one without transformation.\n")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="tunco2pro_blender.zip"'})


@app.get("/api/figures")
def api_figures_list():
    """Publication figures the engine can draw from the current project (see tunco2pro.figures)."""
    from . import figures as F
    return {"figures": F.FIGURES, "project_free": sorted(F.PROJECT_FREE), "formats": list(F.FORMATS)}


class FigureRequest(BaseModel):
    project: ProjectInput | None = None
    options: dict = {}


@app.post("/api/figures/{name}")
def api_figure(name: str, req: FigureRequest, fmt: str = Query("pdf", pattern="^(pdf|svg|png|json)$"),
               dpi: int = Query(1000, ge=72, le=2400)):
    """One figure as PDF, SVG or PNG (or its numbers as JSON), drawn for print from the project as sent."""
    from . import figures as F
    if name not in F.FIGURES:
        raise HTTPException(404, f"unknown figure; one of {', '.join(F.FIGURES)}")
    try:
        if fmt == "json":
            fig, data = (F.MAKERS[name](**req.options) if name in F.PROJECT_FREE else F.MAKERS[name](req.project, **req.options))
            F.to_bytes(fig, "pdf"); return data
        data, _ = F.render(name, req.project, fmt, dpi, **req.options)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except ImportError as e:
        raise HTTPException(501, f"{e.name} not installed: pip install 'tunco2pro[figures]'")
    return Response(data, media_type=F.FORMATS[fmt],
                    headers={"Content-Disposition": f'attachment; filename="tunco2pro-{name}.{fmt}"'})


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


_ROOT = WEB.parents[2]  # repository root when run from a source checkout
_DOCS = {"README.md": _ROOT / "README.md", "CHANGELOG.md": _ROOT / "CHANGELOG.md",
         **{f"docs/{p.name}": p for p in (_ROOT / "docs").glob("*.md")}} if (_ROOT / "README.md").exists() else {}


@app.get("/docs-md/{name:path}", response_class=HTMLResponse)
def doc_page(name: str):
    """The Markdown documentation, shown as a plain page from the Help menu (source checkout only)."""
    path = _DOCS.get(name)
    if path is None or not path.exists():
        raise HTTPException(404, "document not found")
    text = html_mod.escape(path.read_text(encoding="utf-8"))
    # relative links between the Markdown files, and web links, become anchors
    text = re_mod.sub(r"\[([^\]]+)\]\((?:docs/)?([A-Za-z_]+\.md)\)",
                      lambda m: f'<a href="/docs-md/{"README.md" if m.group(2) == "README.md" else "docs/" + m.group(2)}">{m.group(1)}</a>', text)
    text = re_mod.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><title>{html_mod.escape(name)} - TunCO2 Pro</title>"
                        "<style>body{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#222}"
                        "pre{white-space:pre-wrap;word-break:break-word}</style>"
                        f"<p><a href='/'>TunCO2 Pro</a> | <a href='/docs-md/README.md'>README</a></p><pre>{text}</pre>")


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


def run(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", port)))
