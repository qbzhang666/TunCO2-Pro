"""Parametric segmental lining geometry and exports (glTF, IFC 4.3, Rhino .3dm).

Replaces the Rhino/Grasshopper + Speckle chain of v1. Rings are built as
annular-sector solids (straight alignment for the MVP), staggered ring to ring,
with a narrower key segment. Carbon per segment is attached as metadata.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh

from .models import Geometry


@dataclass
class Segment:
    ring: int
    index: int
    is_key: bool
    start_deg: float
    sweep_deg: float
    vertices: np.ndarray  # (n, 3)
    faces: np.ndarray     # (m, 3)
    volume_m3: float


def _sector_solid(r_in, r_out, a0, a1, z0, z1, n_arc):
    a = np.linspace(a0, a1, n_arc + 1)
    ci, si = np.cos(a), np.sin(a)
    # ring axis along +Y (tunnel direction); cross-section in X-Z plane
    rings = []
    for r, z in ((r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1)):
        rings.append(np.column_stack([r * ci, np.full_like(a, z), r * si]))
    V = np.vstack(rings)
    n = n_arc + 1
    F = []
    loops = [(0, 1), (1, 2), (2, 3), (3, 0)]  # inner-front, front face, outer... quads between rings
    for la, lb in loops:
        for i in range(n_arc):
            p, q = la * n + i, la * n + i + 1
            r_, s_ = lb * n + i + 1, lb * n + i
            F += [[p, q, r_], [p, r_, s_]]
    # end caps (radial joint faces)
    for i in (0, n_arc):
        idx = [0 * n + i, 1 * n + i, 2 * n + i, 3 * n + i]
        if i == 0:
            F += [[idx[0], idx[1], idx[2]], [idx[0], idx[2], idx[3]]]
        else:
            F += [[idx[0], idx[3], idx[2]], [idx[0], idx[2], idx[1]]]
    mesh = trimesh.Trimesh(V, np.array(F), process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def build_rings(g: Geometry, n_rings: int = 8, joint_deg: float = 0.4, n_arc: int = 16) -> list[Segment]:
    r_in = g.inner_diameter_m / 2
    r_out = r_in + g.lining_thickness_m
    n = g.segments_per_ring
    key = g.key_angle_deg
    normal = (360.0 - key) / (n - 1)
    segs: list[Segment] = []
    for ring in range(n_rings):
        z0, z1 = ring * g.ring_width_m, (ring + 1) * g.ring_width_m - 0.01
        offset = 90.0 + (normal / 2 if ring % 2 else 0.0)  # stagger joints; key near crown
        start = offset - key / 2
        sweeps = [key] + [normal] * (n - 1)
        for i, sw in enumerate(sweeps):
            a0 = math.radians(start + joint_deg / 2)
            a1 = math.radians(start + sw - joint_deg / 2)
            m = _sector_solid(r_in, r_out, a0, a1, z0, z1, max(2, int(n_arc * sw / 60)))
            segs.append(Segment(ring, i, i == 0, start, sw, np.asarray(m.vertices), np.asarray(m.faces),
                                float(abs(m.volume))))
            start += sw
    return segs


# ---------------------------------------------------------------------------
_PALETTE = {"key": [214, 110, 66, 255], "even": [150, 158, 168, 255], "odd": [124, 134, 146, 255]}


def to_glb(segs: list[Segment], carbon_kg_per_m3: float | None = None) -> bytes:
    scene = trimesh.Scene()
    for s in segs:
        m = trimesh.Trimesh(s.vertices, s.faces, process=False)
        col = _PALETTE["key"] if s.is_key else (_PALETTE["even"] if s.ring % 2 == 0 else _PALETTE["odd"])
        m.visual.face_colors = np.tile(col, (len(s.faces), 1))
        extras = {"ring": s.ring, "segment": s.index, "key": s.is_key, "volume_m3": round(s.volume_m3, 4)}
        if carbon_kg_per_m3 is not None:
            extras["A1A3_kgCO2e"] = round(s.volume_m3 * carbon_kg_per_m3, 1)
        m.metadata["extras"] = extras
        scene.add_geometry(m, node_name=f"R{s.ring:03d}_S{s.index}", geom_name=f"R{s.ring:03d}_S{s.index}")
    return scene.export(file_type="glb", include_normals=False)


def to_ifc(segs: list[Segment], path: str, project_name: str = "TunCO2 Pro",
           carbon_kg_per_m3: float | None = None, concrete_ecf: float | None = None) -> str:
    """IFC 4.3 (IFC4X3_ADD2) file: site > facility > lining segments with carbon Psets."""
    import ifcopenshell
    import ifcopenshell.api as api

    f = api.run("project.create_file", version="IFC4X3_ADD2")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=project_name)
    length = api.run("unit.add_si_unit", f, unit_type="LENGTHUNIT")          # metre (the default would be mm)
    area = api.run("unit.add_si_unit", f, unit_type="AREAUNIT")
    volume = api.run("unit.add_si_unit", f, unit_type="VOLUMEUNIT")
    api.run("unit.assign_unit", f, units=[length, area, volume])
    ctx = api.run("context.add_context", f, context_type="Model")
    crs = route_info.get("crs")
    if crs:  # georeference: local metres about the project origin 
        pcrs = f.createIfcProjectedCRS(Name=f"EPSG:{crs['epsg']}", Description=crs.get("name", ""),
                                       VerticalDatum=crs.get("height_datum", ""), MapUnit=length)
        f.createIfcMapConversion(SourceCRS=ctx, TargetCRS=pcrs, Eastings=crs["origin_easting"],
                                 Northings=crs["origin_northing"], OrthogonalHeight=crs["origin_height"],
                                 XAxisAbscissa=1.0, XAxisOrdinate=0.0, Scale=1.0)
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                   target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    fac = api.run("root.create_entity", f, ifc_class="IfcFacility", name="Tunnel")
    api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[fac])
    for s in segs:
        el = api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy",
                     name=f"Ring {s.ring:03d} Segment {s.index}{' (key)' if s.is_key else ''}")
        el.ObjectType = "TunnelLiningSegment"
        rep = api.run("geometry.add_mesh_representation", f, context=body,
                      vertices=[s.vertices.tolist()], faces=[s.faces.tolist()])
        api.run("geometry.assign_representation", f, product=el, representation=rep)
        api.run("spatial.assign_container", f, relating_structure=fac, products=[el])
        pset = api.run("pset.add_pset", f, product=el, name="Pset_TunCO2_Carbon")
        props = {"RingNumber": s.ring, "SegmentIndex": s.index, "IsKeySegment": s.is_key,
                 "NetVolume_m3": round(s.volume_m3, 4), "LifeCycleModules": "A1-A3"}
        if carbon_kg_per_m3 is not None:
            props["EmbodiedCarbon_A1A3_kgCO2e"] = round(s.volume_m3 * carbon_kg_per_m3, 2)
        if concrete_ecf is not None:
            props["ConcreteECF_kgCO2e_per_m3"] = round(concrete_ecf, 2)
        api.run("pset.edit_pset", f, pset=pset, properties=props)
    f.write(path)
    return path


def to_3dm(segs: list[Segment], path: str, carbon_kg_per_m3: float | None = None) -> str:
    """Rhino .3dm via rhino3dm (MIT) - no Rhino licence required."""
    import rhino3dm as r3

    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Meters
    for s in segs:
        m = r3.Mesh()
        for v in s.vertices:
            m.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for a, b, c in s.faces:
            m.Faces.AddFace(int(a), int(b), int(c))
        m.Normals.ComputeNormals()
        attr = r3.ObjectAttributes()
        attr.Name = f"R{s.ring:03d}_S{s.index}"
        attr.SetUserString("volume_m3", f"{s.volume_m3:.4f}")
        if carbon_kg_per_m3 is not None:
            attr.SetUserString("A1A3_kgCO2e", f"{s.volume_m3 * carbon_kg_per_m3:.1f}")
        model.Objects.AddMesh(m, attr)
    model.Write(path, 8)
    return path


# ===========================================================================
# Route geometry at a chosen level of detail (Part 1 / Part 3 digitalisation)
# ===========================================================================
LOD_CONTENT = {
    100: "Excavated envelope per chainage piece (massing)",
    200: "Lining, annulus grout and invert backfill as solids per piece",
    300: "Segmental rings (with key) + grout + invert per ring",
    400: "LoD 300 + rail/road deck slab",
    500: "LoD 400 with as-built flags for construction-stage reporting",
}
KIND_COLOR = {"envelope": [150, 158, 168, 255], "lining": [150, 158, 168, 255], "segment": [150, 158, 168, 255],
              "key": [214, 110, 66, 255], "grout": [110, 160, 220, 255], "invert": [27, 175, 122, 255],
              "deck": [120, 100, 80, 255]}


@dataclass
class Element:
    kind: str
    zone: str
    ch_from: float
    ch_to: float
    ring: int | None
    index: int | None
    vertices: np.ndarray
    faces: np.ndarray
    volume_m3: float
    carbon_kg: float = 0.0


def _to_world(V: np.ndarray, P0, T, N, U) -> np.ndarray:
    return P0 + np.outer(V[:, 0], N) + np.outer(V[:, 1], T) + np.outer(V[:, 2], U)


def _prism(poly_xz: list[tuple[float, float]], L: float):
    """Extrude a convex polygon (x, z) along local y by L."""
    n = len(poly_xz)
    V = [(x, 0.0, z) for x, z in poly_xz] + [(x, L, z) for x, z in poly_xz]
    F = []
    for i in range(1, n - 1):
        F += [[0, i + 1, i], [n, n + i, n + i + 1]]
    for i in range(n):
        j = (i + 1) % n
        F += [[i, j, n + j], [i, n + j, n + i]]
    m = trimesh.Trimesh(np.array(V), np.array(F), process=True)
    if m.volume < 0:
        m.invert()
    return m


def _annulus(r_in, r_out, L, n_arc=48):
    ms = [_sector_solid(r_in, r_out, a, a + math.pi, 0.0, L, n_arc // 2) for a in (0.0, math.pi)]
    return trimesh.util.concatenate(ms)


def _invert(r, theta_deg, L, n=24):
    th = math.radians(theta_deg)
    a0, a1 = -math.pi / 2 - th / 2, -math.pi / 2 + th / 2
    pts = [(r * math.cos(a), r * math.sin(a)) for a in np.linspace(a0, a1, n)]
    return _prism(pts, L), pts


def route_elements(p, lod: int = 300, max_rings: int = 240, max_pieces_per_zone: int = 40,
                   per_m3: dict | None = None) -> tuple[list[Element], dict]:
    """Build elements along the route. ``per_m3`` = carbon factors by kind (kg per m3)."""
    from .models import Route
    from .route import zone_project
    route = p.route or Route()
    al = route.alignment
    per_m3 = per_m3 or {}
    zones = sorted(route.zones, key=lambda z: z.ch_from)
    total_rings = sum(int(z.length_m / p.geometry.ring_width_m) for z in zones)
    per_zone = max(5, max_rings // max(1, len(zones)))
    truncated = lod >= 300 and total_rings > max_rings
    els: list[Element] = []
    for z in zones:
        q = zone_project(p, z)
        g = q.geometry
        ri, t = g.inner_diameter_m / 2, g.lining_thickness_m
        ro, rt = ri + t, g.tbm_diameter_m / 2
        theta = q.invert.theta_deg if q.invert.by == "theta" else 2 * math.degrees(math.asin(min(1, q.invert.chord_m / g.inner_diameter_m)))
        n_rings = int(z.length_m / g.ring_width_m)
        pieces = []  # (chainage, length, ring index or None, segmented?)
        if lod >= 300:
            k_seg = min(n_rings, per_zone) if truncated else n_rings
            pieces += [(z.ch_from + k * g.ring_width_m, g.ring_width_m, k, True) for k in range(k_seg)]
            rest0, rest = z.ch_from + k_seg * g.ring_width_m, z.length_m - k_seg * g.ring_width_m
        else:
            rest0, rest = z.ch_from, z.length_m
        if rest > 1e-6:
            n = max(1, min(max_pieces_per_zone, int(rest / (4 * g.ring_width_m)) or 1))
            Lp = rest / n
            pieces += [(rest0 + k * Lp, Lp, None, False) for k in range(n)]
        for ch, L, k, segmented in pieces:
            P0, T, N, U = al.frame(ch)
            parts = []
            if lod == 100:
                parts.append(("envelope", None, _annulus(ri, rt, L)))
            else:
                if segmented:
                    local = Geometry(**{**g.model_dump(), "ring_width_m": L + 0.01})
                    for s in build_rings(local, n_rings=1):
                        s_mesh = trimesh.Trimesh(s.vertices, s.faces, process=False)
                        parts.append(("key" if s.is_key else "segment", s.index, s_mesh))
                else:
                    parts.append(("lining", None, _annulus(ri, ro, L)))
                if rt > ro:
                    parts.append(("grout", None, _annulus(ro, rt, L)))
                inv, pts = _invert(ri, theta, L)
                parts.append(("invert", None, inv))
                if lod >= 400:
                    top = max(z_ for _, z_ in pts)
                    xs = [x for x, _ in pts]
                    w = (max(xs) - min(xs)) * 0.9
                    parts.append(("deck", None, _prism([(-w / 2, top), (w / 2, top), (w / 2, top + 0.3), (-w / 2, top + 0.3)], L)))
            for kind, idx, m in parts:
                V = _to_world(np.asarray(m.vertices), P0, T, N, U)
                vol = float(abs(m.volume))
                key = "lining" if kind in ("segment", "key", "lining") else kind
                els.append(Element(kind, z.name, ch, ch + L, k, idx, V, np.asarray(m.faces),
                                   vol, vol * per_m3.get(key, 0.0)))
    meta = {"lod": lod, "lod_content": LOD_CONTENT[lod], "elements": len(els),
            "note": (f"Segmental detail shown for the first {per_zone} rings of each zone; the rest of each zone is "
                     "modelled as continuous solids. Report quantities cover the full route." if truncated else "")}
    return els, meta


def elements_to_glb(els: list[Element]) -> bytes:
    scene = trimesh.Scene()
    for i, e in enumerate(els):
        m = trimesh.Trimesh(e.vertices, e.faces, process=False)
        col = KIND_COLOR.get(e.kind, [150, 150, 150, 255])
        if e.kind == "segment" and e.ring is not None and e.ring % 2:
            col = [124, 134, 146, 255]
        m.visual.face_colors = np.tile(col, (len(e.faces), 1))
        m.metadata["extras"] = {"kind": e.kind, "zone": e.zone, "ch_from": round(e.ch_from, 2),
                                "ch_to": round(e.ch_to, 2), "volume_m3": round(e.volume_m3, 3),
                                "A1A3_kgCO2e": round(e.carbon_kg, 1)}
        scene.add_geometry(m, node_name=f"{e.kind}_{i}", geom_name=f"{e.kind}_{i}")
    return scene.export(file_type="glb", include_normals=False)


def elements_to_ifc(els: list[Element], path: str, project_name: str, meta: dict, route_info: dict) -> str:
    import ifcopenshell.api as api
    f = api.run("project.create_file", version="IFC4X3_ADD2")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=project_name)
    length = api.run("unit.add_si_unit", f, unit_type="LENGTHUNIT")          # metre (the default would be mm)
    area = api.run("unit.add_si_unit", f, unit_type="AREAUNIT")
    volume = api.run("unit.add_si_unit", f, unit_type="VOLUMEUNIT")
    api.run("unit.assign_unit", f, units=[length, area, volume])
    ctx = api.run("context.add_context", f, context_type="Model")
    crs = route_info.get("crs")
    if crs:  # georeference: local metres about the project origin 
        pcrs = f.createIfcProjectedCRS(Name=f"EPSG:{crs['epsg']}", Description=crs.get("name", ""),
                                       VerticalDatum=crs.get("height_datum", ""), MapUnit=length)
        f.createIfcMapConversion(SourceCRS=ctx, TargetCRS=pcrs, Eastings=crs["origin_easting"],
                                 Northings=crs["origin_northing"], OrthogonalHeight=crs["origin_height"],
                                 XAxisAbscissa=1.0, XAxisOrdinate=0.0, Scale=1.0)
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    fac = api.run("root.create_entity", f, ifc_class="IfcFacility", name=route_info.get("name", "Tunnel"))
    api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[fac])
    ps = api.run("pset.add_pset", f, product=fac, name="Pset_TunCO2_Route")
    api.run("pset.edit_pset", f, pset=ps, properties={"LevelOfDetail": meta["lod"], "LoDContent": meta["lod_content"],
            "AlignmentLength_m": round(route_info.get("length_m", 0.0), 2), "Note": meta.get("note", "")})
    names = {"envelope": "Excavated envelope", "lining": "Segmental lining", "segment": "Lining segment",
             "key": "Key segment", "grout": "Annulus grout", "invert": "Invert backfill", "deck": "Rail/road deck"}
    for e in els:
        el = api.run("root.create_entity", f, ifc_class="IfcBuildingElementProxy",
                     name=f"{names[e.kind]} {e.zone} Ch {e.ch_from:.1f}")
        el.ObjectType = names[e.kind]
        rep = api.run("geometry.add_mesh_representation", f, context=body, vertices=[e.vertices.tolist()], faces=[e.faces.tolist()])
        api.run("geometry.assign_representation", f, product=el, representation=rep)
        api.run("spatial.assign_container", f, relating_structure=fac, products=[el])
        pset = api.run("pset.add_pset", f, product=el, name="Pset_TunCO2_Carbon")
        props = {"Zone": e.zone, "ChainageFrom_m": round(e.ch_from, 3), "ChainageTo_m": round(e.ch_to, 3),
                 "NetVolume_m3": round(e.volume_m3, 4), "EmbodiedCarbon_A1A3_kgCO2e": round(e.carbon_kg, 2),
                 "LifeCycleModules": "A1-A3", "LevelOfDetail": meta["lod"]}
        if e.ring is not None:
            props["RingNumber"] = e.ring
        if e.index is not None:
            props["SegmentIndex"] = e.index; props["IsKeySegment"] = e.kind == "key"
        api.run("pset.edit_pset", f, pset=pset, properties=props)
    f.write(path)
    return path


def elements_to_3dm(els: list[Element], path: str) -> str:
    import rhino3dm as r3
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Meters
    for i, e in enumerate(els):
        m = r3.Mesh()
        for v in e.vertices:
            m.Vertices.Add(float(v[0]), float(v[1]), float(v[2]))
        for a, b, c in e.faces:
            m.Faces.AddFace(int(a), int(b), int(c))
        m.Normals.ComputeNormals()
        attr = r3.ObjectAttributes()
        attr.Name = f"{e.kind}_{e.zone}_{e.ch_from:.1f}"
        for k, v in (("kind", e.kind), ("zone", e.zone), ("ch_from", f"{e.ch_from:.2f}"), ("ch_to", f"{e.ch_to:.2f}"),
                     ("volume_m3", f"{e.volume_m3:.4f}"), ("A1A3_kgCO2e", f"{e.carbon_kg:.1f}")):
            attr.SetUserString(k, v)
        model.Objects.AddMesh(m, attr)
    model.Write(path, 8)
    return path
