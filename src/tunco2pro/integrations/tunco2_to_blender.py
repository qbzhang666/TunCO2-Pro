# SPDX-License-Identifier: GPL-3.0-or-later
# This script runs inside Blender and is licensed GPL-3.0-or-later for compatibility
# with Blender; TunCO2 Pro itself is MIT and exchanges data with it by files only.
"""tunco2_to_blender.py - bring a TunCO2 Pro route into Blender (4.2+ / 5.x).

    blender --python tunco2_to_blender.py -- <folder with tunco2pro_scene.json>
    # or: open in Blender's Scripting tab and Run Script (reads the script's folder)

Builds, in a "TunCO2 Pro" collection:
  * the lining model (tunco2pro_route.glb), rotated back from glTF y-up to z-up;
  * one ribbon per ground zone above the crown, coloured by kgCO2e/m, with the
    zone's unit, cover, carbon, FoS and TBM ratings as custom properties;
  * the selected TBM type at the face, scaled to the project diameter.

Coordinates are local metres about the project origin given in the CRS file,
so the model lands on any terrain, building or IFC model prepared in the same
frame without any transform.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Vector


def _folder():
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args:
            return os.path.abspath(args[0])
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in par.children]:
        par.children.link(c)
    return c


def _material(name, rgb, alpha=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Roughness"].default_value = 0.6
        if alpha < 1:
            b.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*rgb, alpha)
    return m


def _import_glb(path, coll, name):
    """Import a glb (written z-up by TunCO2 Pro) under an empty that undoes the importer's y-up conversion."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    fix = bpy.data.objects.new(name, None)
    fix.rotation_euler = Euler((-math.pi / 2, 0, 0))
    coll.objects.link(fix)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        if o.parent is None:
            o.parent = fix
    return fix


def main(folder=None):
    folder = folder or _folder()
    with open(os.path.join(folder, "tunco2pro_scene.json"), encoding="utf-8") as f:
        sc = json.load(f)
    root = _collection("TunCO2 Pro")
    root["crs"] = json.dumps(sc["frame"]["crs"])

    lining = _collection("TunCO2 lining", root)
    glb = os.path.join(folder, "tunco2pro_route.glb")
    if os.path.exists(glb):
        _import_glb(glb, lining, "TunCO2 lining (z-up)")

    zc = _collection("TunCO2 ground zones", root)
    D = sc["tbm"]["diameter_m"]
    for z in sc["zones"]:
        cu = bpy.data.curves.new(f"zone_{z['index']}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.6
        cu.bevel_resolution = 2
        sp = cu.splines.new("POLY")
        pts = z["polyline"]
        sp.points.add(len(pts) - 1)
        for p, q in zip(sp.points, pts):
            p.co = (q[0], q[1], q[2] + D / 2 + 1.0, 1.0)
        ob = bpy.data.objects.new(f"{z['index']:02d} {z['name']}", cu)
        ob.data.materials.append(_material(f"tunco2_zone_{z['index']}", z["colour_carbon"]))
        for k in ("unit", "ground_kind", "ch_from", "ch_to", "cover_m", "kgCO2e_per_m", "tCO2e", "fos"):
            if z.get(k) is not None:
                ob[k] = z[k]
        if z.get("tbm"):
            ob["tbm_ratings"] = json.dumps(z["tbm"])
        zc.objects.link(ob)

    t = sc["tbm"]
    if t.get("model") and os.path.exists(os.path.join(folder, t["model"])):
        tc = _collection("TunCO2 TBM", root)
        holder = bpy.data.objects.new(f"TBM {t['type']}", None)
        d = Vector(t["direction"]).normalized()
        yaw, pitch = math.atan2(d.y, d.x), math.asin(max(-1, min(1, d.z)))
        s = D / t["model_envelope_m"]
        holder.matrix_world = (Matrix.Translation(Vector(t["position"])) @ Matrix.Rotation(yaw, 4, "Z")
                               @ Matrix.Rotation(-pitch, 4, "Y") @ Matrix.Scale(s, 4))
        tc.objects.link(holder)
        fix = _import_glb(os.path.join(folder, t["model"]), tc, "TBM model (z-up)")
        fix.parent = holder
    print(f"TunCO2 Pro: {len(sc['zones'])} zones, alignment {sc['alignment']['name']}")
    return root


if __name__ == "__main__":
    main()
