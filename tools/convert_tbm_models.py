"""Convert six Rhino (.3dm) TBM-type models into light glTF previews for the
TunCO2 Pro viewer.

    python tools/convert_tbm_models.py <folder with the six .3dm files> [--out src/tunco2pro/web/assets/tbm]

What it does, per model:
  * keeps the machine (20_TBM/...) within KEEP_BEHIND_M of the face, drops the
    back-up train, the schematic bore wall and the lining (TunCO2 Pro draws its own);
  * meshes Breps: cached render meshes where Rhino saved them; otherwise planar
    faces are triangulated from their edge loops and curved faces from a UV grid
    (the generated kit parts carry no render mesh). Trimmed curved faces are
    shown untrimmed - a preview, not a survey;
  * re-axes to the TunCO2 convention: face at local x = 0, +x = drive direction,
    z up, metres; bore axis on x;
  * decimates each layer group so a model is ~60k triangles;
  * writes <type>.glb plus tbm_models.json (shield diameter, length, layers).

The models are expected on one common shield envelope (ENVELOPE_M); the viewer
scales them to the project's TBM diameter, so they are generic representations
of each machine type, not designs.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rhino3dm
import trimesh

FILES = {
    "gripper": "01_gripper_TBM.3dm",
    "single_shield": "02_single_shield_TBM.3dm",
    "double_shield": "03_double_shield_TBM.3dm",
    "epb": "04_EPB_shield.3dm",
    "slurry": "05_slurry_shield.3dm",
    "multi_mode": "06_multi_mode_shield.3dm",
}
KEEP_BEHIND_M = 24.0
ENVELOPE_M = 10.453  # common shield envelope of the six models (m)
SKIP = ("40_Lining", "BoreWall")
TARGET_TRIS = 60_000
FACE_LAYERS = ("Cutterhead", "DiscCutters", "CutterHead")
SHIELD_LAYERS = ("ShieldSkin", "ShieldFrontCollar", "ShieldMiddle", "ShieldTail", "Cutterhead")


def _mesh_arrays(m: rhino3dm.Mesh):
    V = np.array([[v.X, v.Y, v.Z] for v in m.Vertices], float)
    T = []
    for i in range(len(m.Faces)):
        a, b, c, d = m.Faces[i]
        T.append((a, b, c))
        if d != c:
            T.append((a, c, d))
    return V, np.array(T, int).reshape(-1, 3)


def _sample_curve(c, n=None):
    d = c.Domain
    if n is None:
        n = 2 if c.IsLinear() else 24
    ts = np.linspace(d.T0, d.T1, n)
    return np.array([[p.X, p.Y, p.Z] for p in (c.PointAt(t) for t in ts)])


def _loop_points(brep, loop):
    pts = []
    for k in range(loop.TrimCount):
        tr = loop.Trims[k]
        e = brep.Edges[tr.EdgeIndex]
        P = _sample_curve(e)
        rev = tr.IsReversed() if callable(tr.IsReversed) else tr.IsReversed
        if rev:
            P = P[::-1]
        if pts and np.linalg.norm(pts[-1][-1] - P[0]) > np.linalg.norm(pts[-1][-1] - P[-1]):
            P = P[::-1]
        pts.append(P[:-1] if len(P) > 1 else P)
    return np.vstack(pts) if pts else np.zeros((0, 3))


def _planar_face(brep, face):
    import mapbox_earcut as earcut
    loops = [face.Loops[i] for i in range(len(face.Loops))]
    rings = [_loop_points(brep, lp) for lp in loops]
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return None
    allp = np.vstack(rings)
    c = allp.mean(0)
    _, _, vt = np.linalg.svd(allp - c)
    e1, e2, n = vt[0], vt[1], vt[2]
    uv = [np.c_[(r - c) @ e1, (r - c) @ e2] for r in rings]
    ends = np.cumsum([len(r) for r in uv]).astype(np.uint32)
    try:
        tri = earcut.triangulate_float64(np.vstack(uv), ends).reshape(-1, 3)
    except Exception:  # noqa: BLE001
        return None
    V = allp
    du, dv = face.Domain(0), face.Domain(1)
    fn = face.NormalAt(0.5 * (du.T0 + du.T1), 0.5 * (dv.T0 + dv.T1))
    fn = np.array([fn.X, fn.Y, fn.Z])
    if face.OrientationIsReversed:
        fn = -fn
    if len(tri):
        a, b, cc = V[tri[0, 0]], V[tri[0, 1]], V[tri[0, 2]]
        if np.dot(np.cross(b - a, cc - a), fn) < 0:
            tri = tri[:, ::-1]
    return V, tri


def _grid_face(face):
    du, dv = face.Domain(0), face.Domain(1)
    nu = 2 if face.Degree(0) == 1 and face.SpanCount(0) == 1 else 20
    nv = 2 if face.Degree(1) == 1 and face.SpanCount(1) == 1 else 20
    us, vs = np.linspace(du.T0, du.T1, nu), np.linspace(dv.T0, dv.T1, nv)
    V = np.array([[p.X, p.Y, p.Z] for u in us for v in vs for p in [face.PointAt(u, v)]])
    T = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a, b, c, d = i * nv + j, (i + 1) * nv + j, (i + 1) * nv + j + 1, i * nv + j + 1
            T += [(a, b, c), (a, c, d)]
    T = np.array(T)
    if face.OrientationIsReversed:
        T = T[:, ::-1]
    return V, T


def brep_arrays(brep):
    Vs, Ts, off = [], [], 0
    for i in range(len(brep.Faces)):
        f = brep.Faces[i]
        m = f.GetMesh(rhino3dm.MeshType.Any)
        if m is not None:
            r = _mesh_arrays(m)
        elif f.IsPlanar():
            r = _planar_face(brep, f)
        else:
            r = _grid_face(f)
        if r is None or len(r[1]) == 0:
            continue
        Vs.append(r[0]); Ts.append(r[1] + off); off += len(r[0])
    if not Vs:
        return None
    return np.vstack(Vs), np.vstack(Ts)


def convert(path: Path):
    f = rhino3dm.File3dm.Read(str(path))
    scale = {rhino3dm.UnitSystem.Millimeters: 0.001, rhino3dm.UnitSystem.Meters: 1.0}.get(f.Settings.ModelUnitSystem, 0.001)
    layers = {i: f.Layers[i] for i in range(len(f.Layers))}
    items = []
    for o in f.Objects:
        lp = layers[o.Attributes.LayerIndex].FullPath
        if not lp.startswith("20_TBM") or any(s in lp for s in SKIP):
            continue
        g = o.Geometry
        t = type(g).__name__
        if t not in ("Mesh", "Brep", "Extrusion"):
            continue
        b = g.GetBoundingBox()
        items.append((o, g, t, lp, np.array([b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z]) * scale))
    face_y = max(bb[4] for *_, lp, bb in items if any(k in lp for k in FACE_LAYERS))
    sh = [bb for *_, lp, bb in items if any(k in lp for k in SHIELD_LAYERS)]
    sh = np.array(sh)
    xc = 0.5 * (sh[:, 0].min() + sh[:, 3].max())
    zc = 0.5 * (sh[:, 2].min() + sh[:, 5].max())
    shield_d = max(sh[:, 3].max() - sh[:, 0].min(), sh[:, 5].max() - sh[:, 2].min())

    groups = defaultdict(lambda: [[], [], 0])
    for o, g, t, lp, bb in items:
        cy = 0.5 * (bb[1] + bb[4])
        if cy < face_y - KEEP_BEHIND_M or bb[1] < face_y - KEEP_BEHIND_M - 6:
            continue  # back-up train, and long parts (belts) that run back into it
        if t == "Mesh":
            r = _mesh_arrays(g)
        elif t == "Extrusion":
            m = g.GetMesh(rhino3dm.MeshType.Any)
            r = _mesh_arrays(m) if m is not None else brep_arrays(g.ToBrep(True))
        else:
            r = brep_arrays(g)
        if r is None:
            continue
        V, T = r
        V = V * scale
        # world (X, Y, Z) -> local (x = Y - face, y = -(X - xc), z = Z - zc); a proper rotation
        V = np.c_[V[:, 1] - face_y, -(V[:, 0] - xc), V[:, 2] - zc]
        lay = layers[o.Attributes.LayerIndex]
        col = lay.Color
        if o.Attributes.ColorSource == rhino3dm.ObjectColorSource.ColorFromObject:
            col = o.Attributes.ObjectColor
        key = (lp.split("::", 2)[-1] if lp.count("::") >= 2 else lp, tuple(int(c) for c in col[:3]))
        gr = groups[key]
        gr[0].append(V); gr[1].append(T + gr[2]); gr[2] += len(V)

    total = sum(sum(len(t) for t in g[1]) for g in groups.values())
    ratio = min(1.0, TARGET_TRIS / max(total, 1))
    scene = trimesh.Scene()
    info = []
    for (name, rgb), (Vs, Ts, _) in sorted(groups.items()):
        V, T = np.vstack(Vs), np.vstack(Ts)
        m = trimesh.Trimesh(V, T, process=True)
        if ratio < 1 and len(m.faces) > 400:
            import fast_simplification
            Vd, Td = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int64),
                                                  target_reduction=1 - max(ratio, 0.02))
            m = trimesh.Trimesh(Vd, Td, process=True)
        mat = trimesh.visual.material.PBRMaterial(name=name, baseColorFactor=[*rgb, 255],
                                                   metallicFactor=0.0, roughnessFactor=0.7, doubleSided=True)
        m.visual = trimesh.visual.TextureVisuals(material=mat)
        scene.add_geometry(m, node_name=name.replace("::", "/"), geom_name=name)
        info.append({"layer": name, "rgb": list(rgb), "triangles": int(len(m.faces))})
    ext = scene.bounds
    tails = [bb for *_, lp, bb in items if "ShieldTail" in lp]
    tail_m = face_y - min(b[1] for b in tails) if tails else 1.43 * ENVELOPE_M
    meta = {"envelope_m": ENVELOPE_M, "tail_behind_face_m": round(float(tail_m), 2),
            "shield_diameter_m": round(float(shield_d), 3), "length_m": round(float(-ext[0][0]), 2),
            "triangles": int(sum(i["triangles"] for i in info)), "source_triangles": int(total), "layers": info}
    return scene, meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "src/tunco2pro/web/assets/tbm"))
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    index = {}
    for key, fn in FILES.items():
        p = Path(a.src) / fn
        if not p.exists():
            print("missing", p, file=sys.stderr); continue
        scene, meta = convert(p)
        data = scene.export(file_type="glb")
        (out / f"{key}.glb").write_bytes(data)
        meta.update(bytes=len(data))
        index[key] = meta
        print(f"{key:14s} {meta['triangles']:7d} tris (from {meta['source_triangles']}), "
              f"{len(data)/1e6:5.2f} MB, D {meta['shield_diameter_m']} m, L {meta['length_m']} m")
    (out / "tbm_models.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
