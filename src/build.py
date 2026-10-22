"""build.py - full assembly of the chibi maid. Renders previews and saves .blend."""
import bpy
import sys
import os
import math
from mathutils import Vector

# 仓库自带相对路径：脚本放在 <repo>/src/build.py，模型与渲染输出落在 <repo>/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mcore as C
import mprop as P
import mmat as M
import mhead as HD
import mhair as HR
import mbody as BD
import mcloth as CL

OUT = os.path.join(ROOT, "renders")
os.makedirs(OUT, exist_ok=True)
DO_RENDER = os.environ.get("MAID_RENDER", "1") != "0"
SAMPLES = int(os.environ.get("MAID_SAMPLES", "96"))
RES = int(os.environ.get("MAID_RES", "900"))
VIEWS = os.environ.get("MAID_VIEWS", "body")


def setup_world_lights():
    w = bpy.data.worlds.new("Studio")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.66, 0.68, 0.72, 1)
    bg.inputs[1].default_value = 0.30
    C.add_area_light("Key", (-0.95, -1.45, 1.55), (0, 0, 0.62), energy=28, size=1.5)
    C.add_area_light("Fill", (1.25, -1.15, 0.62), (0, 0, 0.52), energy=9, size=2.0,
                     color=(0.90, 0.94, 1.0))
    C.add_area_light("Rim", (0.55, 1.30, 1.35), (0, 0, 0.72), energy=16, size=1.1,
                     color=(1.0, 0.96, 0.92))
    C.add_area_light("Bounce", (0.0, -0.6, -0.1), (0, 0, 0.35), energy=4, size=1.4,
                     color=(1.0, 0.95, 0.92))


BODY_VIEWS = {
    "front": ((0.0, -2.70, 0.56), (0, 0, 0.52), 85),
    "q34":   ((-1.75, -2.00, 0.72), (0, 0, 0.52), 85),
    "side":  ((2.70, -0.02, 0.56), (0, 0, 0.52), 85),
    "back":  ((0.0, 2.70, 0.56), (0, 0, 0.52), 85),
    "q34b":  ((1.75, -2.00, 0.72), (0, 0, 0.52), 85),
}
CLOSE_VIEWS = {
    "c_face":  ((0.0, -1.02, 0.762), (0, 0, 0.760), 85),
    "c_torso": ((-0.55, -1.15, 0.70), (0, 0, 0.50), 85),
    "c_hand":  ((-0.45, -0.62, 0.42), (-0.115, -0.09, 0.345), 85),
    "c_feet":  ((-0.30, -0.75, 0.22), (0, 0, 0.075), 85),
    "c_backbow": ((0.35, 0.80, 0.55), (0, 0.07, 0.455), 85),
    "c_head":  ((-0.55, -0.95, 0.95), (0, 0, 0.83), 85),
}


def render_views(tag=""):
    s = bpy.context.scene
    C.setup_render((RES, int(RES * 1.35)), samples=SAMPLES)
    views = dict(CLOSE_VIEWS if VIEWS == "close" else BODY_VIEWS)
    paths = []
    for name, (loc, tgt, lens) in views.items():
        cam = bpy.data.objects.get("Cam_" + name)
        if cam is None:
            cam = C.add_camera("Cam_" + name, loc, tgt, lens=lens)
        p = os.path.join(OUT, "%s%s.png" % (tag, name))
        C.render_to(p, cam)
        paths.append(p)
    return paths


def organise():
    """Group objects into tidy collections for the deliverable .blend."""
    groups = {
        "01_Head": set(),
        "02_Hair": set(),
        "03_Body": set(),
        "04_Dress": set(),
        "05_Apron": set(),
        "06_Details": set(),
    }
    for ob in list(bpy.data.objects):
        n = ob.name
        if n.startswith(("Head", "Ear", "Neck", "Eye", "Iris", "Lash", "LowerLid",
                         "Brow", "Mouth", "RedAccent", "Brow")):
            k = "01_Head"
        elif n.startswith(("Hair", "Fringe", "Lock", "Nape")):
            k = "02_Hair"
        elif n.startswith(("Torso", "Arm", "Leg", "Hand", "Thumb", "Finger", "Palm")):
            k = "03_Body"
        elif n.startswith(("Skirt", "Bodice", "Collar", "Sleeve", "Cuff", "Placket",
                           "Button", "BackStrap", "BackBow", "Strap", "Sock", "Loafer", "Panties")):
            k = "06_Details"
        elif n.startswith(("Apron", "Waistband", "ShoulderRuffle")):
            k = "05_Apron"
        elif n.startswith(("Cam_", "Key", "Fill", "Rim", "Bounce")):
            continue
        else:
            k = "04_Dress"
        groups[k].add(ob)
    root = bpy.data.collections.get("Maid")
    # anything not matched goes to the dress collection
    matched = set()
    for objs in groups.values():
        matched |= objs
    for ob in list(bpy.data.objects):
        if ob.type == "MESH" and ob not in matched:
            groups["04_Dress"].add(ob)
    for name, objs in groups.items():
        if not objs:
            continue
        col = bpy.data.collections.new(name)
        root.children.link(col)
        for ob in objs:
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            col.objects.link(ob)


def fix_hair_neckline():
    """Trim the hair that sinks into the neck/body, close the cut rims and
    taper the side locks so they end in a point instead of a flat disc."""
    import bmesh
    cuts = {"HairCap": 0.6010, "Lock_0": 0.6400, "Lock_0_mir": 0.6400}
    for name, zcut in cuts.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.bisect_plane(
            bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), dist=1e-6,
            plane_co=(0.0, 0.0, zcut), plane_no=(0.0, 0.0, 1.0), clear_inner=True)
        boundary = [e for e in bm.edges if len(e.link_faces) == 1]
        if boundary:
            bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
        if name.startswith("Lock"):
            zmin = min(v.co.z for v in bm.verts)
            ring = [v for v in bm.verts if v.co.z < zmin + 0.0025]
            if ring:
                cx = sum(v.co.x for v in ring) / len(ring)
                cy = sum(v.co.y for v in ring) / len(ring)
                for v in ring:
                    v.co.x = cx + (v.co.x - cx) * 0.12
                    v.co.y = cy + (v.co.y - cy) * 0.12
                    v.co.z -= 0.010
                bmesh.ops.remove_doubles(bm, verts=ring, dist=0.0012)
                mid = [v for v in bm.verts if zmin + 0.0025 <= v.co.z < zmin + 0.0300]
                for v in mid:
                    t = (v.co.z - zmin) / 0.0300
                    k = 0.35 + 0.65 * t
                    v.co.x = cx + (v.co.x - cx) * k
                    v.co.y = cy + (v.co.y - cy) * k
        bm.normal_update()
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()
        for p in ob.data.polygons:
            p.use_smooth = True
        print("hair trimmed: %-11s verts=%d" % (name, len(ob.data.vertices)))


def assert_hair_outside_body():
    """Report (and push out) any hair vertex still inside the head/neck/torso."""
    from mathutils.bvhtree import BVHTree
    verts, faces = [], []
    for nm in ("Head", "Neck", "Torso", "Bodice"):
        ob = bpy.data.objects.get(nm)
        if not ob or ob.type != "MESH":
            continue
        mw = ob.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in ob.data.vertices]
        for p in ob.data.polygons:
            faces.append([base + i for i in p.vertices])
    if not faces:
        return
    bvh = BVHTree.FromPolygons(verts, faces, all_triangles=False, epsilon=0.0)

    def _count_and_push(push):
        pushed = 0
        for nm in ("HairCap", "FringeMass", "Lock_0", "Lock_0_mir"):
            ob = bpy.data.objects.get(nm)
            if not ob:
                continue
            mw = ob.matrix_world
            mwi = mw.inverted()
            moved = 0
            for v in ob.data.vertices:
                wco = mw @ v.co
                hit = bvh.find_nearest(wco)
                if hit[0] is None:
                    continue
                p, n, _idx, _d = hit
                if (wco - p).dot(n) < 0.0:
                    moved += 1
                    if push:
                        v.co = mwi @ (p + n * 0.0035)
            if moved and push:
                ob.data.update()
                print("hair pushed out: %-11s %d verts" % (nm, moved))
            pushed += moved
        return pushed

    pushed = _count_and_push(True)
    remaining = _count_and_push(False)
    print("HAIR INSIDE BODY: pushed=%d remaining=%d" % (pushed, remaining))


def rebuild_headband(mats):
    """Thick semicircular band hugging the skull (the shape approved by the client).
    Replaces the earlier crescent + separate ruffle with a single band."""
    import bmesh
    old = bpy.data.objects.get("Headband")
    coll = None
    if old:
        coll = old.users_collection[0] if old.users_collection else None
        bpy.data.objects.remove(old, do_unlink=True)
    n, hw = 150, 0.0195
    verts, faces = [], []
    for i in range(n):
        t = i / (n - 1)
        a = math.radians(-106.0 + 212.0 * t)
        k = abs(a) / math.radians(106.0)
        z = 0.9080 - 0.0300 * (1.0 - math.cos(math.pi * k)) * 0.5
        lobe = 0.0030 * math.cos(2.0 * math.pi * 11.0 * t + 0.4)
        top = HR.hair_point(a, min(0.9620, z + hw + lobe), 0.0110)
        bot = HR.hair_point(a, max(0.6600, z - hw), 0.0110)
        verts += [tuple(top), tuple(bot)]
    for i in range(n - 1):
        faces.append((i * 2 + 1, (i + 1) * 2 + 1, (i + 1) * 2, i * 2))
    me = bpy.data.meshes.new("Headband")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("Headband", me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    sol = ob.modifiers.new("Thickness", "SOLIDIFY")
    sol.thickness = 0.0080
    sol.offset = 0.0
    sol.use_even_offset = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=sol.name)
    sub = ob.modifiers.new("Smooth", "SUBSURF")
    sub.levels = 1
    bpy.ops.object.modifier_apply(modifier=sub.name)
    for v in ob.data.vertices:            # keep it proud of the hair shell
        v.co.x *= 1.075
        v.co.y *= 1.075
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.clear()
    ob.data.materials.append(mats["white"])
    print("headband rebuilt: verts=%d" % len(ob.data.vertices))


def crop_panties(press=0.97, band=0.050, zcut=0.2980):
    """Shorten the briefs to the approved height and press the two panels shut."""
    import bmesh
    ob = bpy.data.objects.get("Panties")
    if ob is None:
        return
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(
        bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), dist=1e-6,
        plane_co=(0.0, 0.0, zcut), plane_no=(0.0, 0.0, 1.0), clear_outer=True)
    zs = [v.co.z for v in bm.verts]
    lo = min(zs)
    for v in bm.verts:
        if v.co.z < lo + band:
            t = 1.0 - (v.co.z - lo) / band
            v.co.y *= (1.0 - press * (t ** 0.85))
    bm.normal_update()
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    for p in ob.data.polygons:
        p.use_smooth = True
    print("panties cropped: verts=%d" % len(ob.data.vertices))


def apply_client_edits(mats):
    """Bake every hand edit the client made, so a fresh rebuild == the shipped model."""
    for o in list(bpy.data.objects):
        if o.name.startswith(("Ear", "Lock_1", "CuffBtn", "ShoulderRuffle", "HeadbandRuffle")):
            print("REMOVED (client edit):", o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    rebuild_headband(mats)
    crop_panties()


def main():
    C.purge_scene()
    mats = M.all_mats()
    print("mats ok")
    head = HD.build_head_group(mats)
    hair = HR.build_hair(mats)
    body = BD.build_body(mats)
    outfit = CL.build_outfit(mats)
    print("parts", len(head), len(hair), len(body), sorted(outfit.keys()))
    setup_world_lights()
    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    organise()
    # always create the cameras (deliverable), render only when asked
    C.setup_render((RES, int(RES * 1.35)), samples=SAMPLES)
    cams = {}
    for name, (loc, tgt, lens) in BODY_VIEWS.items():
        cams[name] = C.add_camera('Cam_' + name, loc, tgt, lens=lens)
    for name, (loc, tgt, lens) in CLOSE_VIEWS.items():
        cams[name] = C.add_camera('Cam_' + name, loc, tgt, lens=lens)
    if DO_RENDER:
        render_views()
    # default camera = three-quarter
    cam = bpy.data.objects.get("Cam_q34")
    if cam:
        bpy.context.scene.camera = cam
    blend = os.path.join(ROOT, "chibi_maid.blend")
    apply_client_edits(mats)
    fix_hair_neckline()
    assert_hair_outside_body()

    tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    verts = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == "MESH")
    print("OBJECTS", len(bpy.data.objects), "FACES", tris, "VERTS", verts)

    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("SAVED", blend)


main()
