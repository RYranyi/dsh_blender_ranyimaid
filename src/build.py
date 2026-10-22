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
    tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == "MESH")
    verts = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == "MESH")
    print("OBJECTS", len(bpy.data.objects), "FACES", tris, "VERTS", verts)
    # default camera = three-quarter
    cam = bpy.data.objects.get("Cam_q34")
    if cam:
        bpy.context.scene.camera = cam
    blend = os.path.join(ROOT, "chibi_maid.blend")
    # the client deleted the ears -- honour that by removing them from the build
    for o in list(bpy.data.objects):
        if o.name.startswith(("Ear", "Lock_1")):
            print("REMOVED (client edit):", o.name)
            bpy.data.objects.remove(o, do_unlink=True)

    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("SAVED", blend)


main()
