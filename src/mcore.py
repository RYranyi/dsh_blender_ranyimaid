"""mcore.py - procedural geometry core for the chibi maid build.

World convention:
  +Z up, character faces -Y, +X = character's LEFT.
  Total height 1.0 m (chibi figurine scale). Feet on z=0.
Everything here is generated from scratch; no external assets.
"""
import bpy
import bmesh
import math
from math import sin, cos, pi, sqrt, exp, atan2, asin, acos, tan
from mathutils import Vector, Matrix, Euler

TAU = 2.0 * pi
SCENE = None


# ---------------------------------------------------------------- colour utils
def _s2l(c):
    c = float(c)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(s, a=1.0):
    """sRGB hex -> linear RGBA tuple."""
    s = s.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_s2l(r), _s2l(g), _s2l(b), a)


def mixc(c1, c2, t):
    return tuple(c1[i] * (1 - t) + c2[i] * t for i in range(len(c1)))


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else (hi if x > hi else x)


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0) if e1 != e0 else 0.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_v(a, b, t):
    return Vector(a) * (1 - t) + Vector(b) * t


# ---------------------------------------------------------------- scene helpers
def get_collection(name="Maid"):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def purge_scene():
    """Remove all objects (and orphan data) so a rebuild is deterministic."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for blocks in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                   bpy.data.armatures, bpy.data.lights, bpy.data.cameras,
                   bpy.data.images, bpy.data.node_groups):
        for b in list(blocks):
            try:
                blocks.remove(b)
            except Exception:
                pass
    for col in list(bpy.data.collections):
        if col.name != "Collection":
            bpy.data.collections.remove(col)


def new_obj(name, verts, faces, colname="Maid", smooth=True, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(verbose=False, clean_customdata=False)
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    get_collection(colname).objects.link(ob)
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        for li, loop in enumerate(me.loops):
            uvl.data[li].uv = uvs[loop.vertex_index]
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return ob


def recalc_normals(ob, inside=False):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if inside:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()


def set_vcol(ob, name, colors, domain="POINT"):
    me = ob.data
    ca = me.color_attributes.get(name)
    if ca is None:
        ca = me.color_attributes.new(name=name, type="FLOAT_COLOR", domain=domain)
    for i, c in enumerate(colors):
        ca.data[i].color = c
    return ca


def orient_faces(ob, axis=1, sign=-1):
    """Force every polygon normal to point along +axis*sign (for decal patches)."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    flip = [f for f in bm.faces if f.normal[axis] * sign < 0]
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)
    bm.to_mesh(me)
    bm.free()
    me.update()
    for p in me.polygons:
        p.use_smooth = True


def mix_rgba(nt, fac=None, a=None, b=None, blend="MIX"):
    """Create a ShaderNodeMix configured for RGBA (avoids socket-name ambiguity)."""
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    n.blend_type = blend
    ins = {s.name: s for s in n.inputs if s.type == "RGBA"}
    out = [s for s in n.outputs if s.type == "RGBA"][0]
    if a is not None:
        ins["A"].default_value = a
    if b is not None:
        ins["B"].default_value = b
    if fac is not None:
        if hasattr(fac, "is_output"):
            nt.links.new(fac, n.inputs[0])
        else:
            n.inputs[0].default_value = fac
    return n, out


# ---------------------------------------------------------------- primitives
def grid(name, fn, nu, nv, close_u=False, close_v=False, colname="Maid", smooth=True):
    """Parametric patch. fn(u,v)->(x,y,z), u,v in [0,1]."""
    verts = []
    cu = nu if close_u else nu + 1
    for j in range(nv + 1):
        v = j / nv
        for i in range(cu):
            u = i / nu
            verts.append(fn(u, v))
    faces = []
    for j in range(nv):
        for i in range(cu if close_u else nu):
            i2 = (i + 1) % cu
            a = j * cu + i
            b = j * cu + i2
            c = (j + 1) * cu + i2
            d = (j + 1) * cu + i
            faces.append((a, b, c, d))
    ob = new_obj(name, verts, faces, colname, smooth)
    return ob


def loft(name, rings, close_v=True, cap0=False, cap1=False, colname="Maid", smooth=True):
    """rings: list of point-lists (equal length). close_v wraps around each ring."""
    n = len(rings[0])
    verts = []
    for r in rings:
        verts.extend(r)
    faces = []
    m = len(rings)
    lim = n if close_v else n - 1
    for j in range(m - 1):
        for i in range(lim):
            i2 = (i + 1) % n
            a = j * n + i
            b = j * n + i2
            c = (j + 1) * n + i2
            d = (j + 1) * n + i
            faces.append((a, b, c, d))
    if cap0:
        faces.append(tuple(range(n - 1, -1, -1)))
    if cap1:
        base = (m - 1) * n
        faces.append(tuple(base + i for i in range(n)))
    return new_obj(name, verts, faces, colname, smooth)


def rings_from_profile(profile, seg, shape=None):
    """profile: list of (rx, ry, z, yc). shape(theta)->(sx,sy) radial modifiers."""
    out = []
    for (rx, ry, z, yc) in profile:
        ring = []
        for i in range(seg):
            th = TAU * i / seg
            sx = sy = 1.0
            if shape:
                sx, sy = shape(th, z)
            ring.append((rx * sx * sin(th), yc - ry * sy * cos(th), z))
        out.append(ring)
    return out


def revolve(name, profile, seg=64, mod=None, colname="Maid", close_v=True):
    """profile: [(r,z)] bottom->top (or any order). mod(theta, i, r, z)->(r,z)."""
    rings = []
    for idx, (r, z) in enumerate(profile):
        ring = []
        for i in range(seg):
            th = TAU * i / seg
            rr, zz = (r, z)
            if mod:
                rr, zz = mod(th, idx, r, z)
            ring.append((rr * sin(th), -rr * cos(th), zz))
        rings.append(ring)
    return loft(name, rings, close_v=close_v, colname=colname)


def sphere(name, c, radii, seg=64, rings=48, colname="Maid"):
    prof = []
    rx, ry, rz = radii
    for j in range(rings + 1):
        phi = pi * j / rings
        prof.append((sin(phi) * 1.0, cos(phi) * 1.0))
    verts = []
    for j in range(rings + 1):
        phi = pi * j / rings
        for i in range(seg):
            th = TAU * i / seg
            verts.append((c[0] + rx * sin(phi) * sin(th),
                          c[1] + ry * sin(phi) * (-cos(th)),
                          c[2] + rz * cos(phi)))
    faces = []
    for j in range(rings):
        for i in range(seg):
            i2 = (i + 1) % seg
            a = j * seg + i
            b = j * seg + i2
            c2 = (j + 1) * seg + i2
            d = (j + 1) * seg + i
            faces.append((a, b, c2, d))
    return new_obj(name, verts, faces, colname)


def polyline_resample(pts, n):
    """Resample a polyline to n points by arc length (Catmull-Rom smoothed)."""
    P = [Vector(p) for p in pts]
    if len(P) < 2:
        return [P[0].copy() for _ in range(n)]
    # densify with catmull-rom
    dense = []
    ext = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    steps = 12
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                                (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                                (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(P[-1])
    # arc length
    L = [0.0]
    for i in range(1, len(dense)):
        L.append(L[-1] + (dense[i] - dense[i - 1]).length)
    total = L[-1]
    out = []
    for k in range(n):
        s = total * k / (n - 1)
        i = 0
        while i < len(L) - 2 and L[i + 1] < s:
            i += 1
        seg = max(1e-9, L[i + 1] - L[i])
        f = (s - L[i]) / seg
        out.append(dense[i] * (1 - f) + dense[i + 1] * f)
    return out


def tube(name, pts, radii, seg=16, caps=True, colname="Maid", up=(0, 0, 1),
         squash=None):
    """Sweep a circle (or ellipse) along a polyline with parallel transport."""
    P = [Vector(p) for p in pts]
    n = len(P)
    if callable(radii):
        R = [radii(i / (n - 1)) for i in range(n)]
    elif isinstance(radii, (list, tuple)):
        R = list(radii)
    else:
        R = [radii] * n
    tangents = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            t = P[i + 1] - P[i - 1]
        tangents.append(t.normalized())
    # initial frame
    ref = Vector(up)
    if abs(ref.dot(tangents[0])) > 0.95:
        ref = Vector((1, 0, 0))
    nrm = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
    frames = []
    for i in range(n):
        if i > 0:
            q = tangents[i - 1].rotation_difference(tangents[i])
            nrm = (q @ nrm).normalized()
        bn = tangents[i].cross(nrm).normalized()
        frames.append((nrm, bn))
    verts = []
    for i in range(n):
        nrm, bn = frames[i]
        sq = 1.0 if squash is None else squash(i / (n - 1))
        for k in range(seg):
            a = TAU * k / seg
            verts.append(tuple(P[i] + nrm * (cos(a) * R[i]) + bn * (sin(a) * R[i] * sq)))
    faces = []
    for i in range(n - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            faces.append((i * seg + k, i * seg + k2, (i + 1) * seg + k2, (i + 1) * seg + k))
    if caps:
        faces.append(tuple(range(seg - 1, -1, -1)))
        b = (n - 1) * seg
        faces.append(tuple(b + k for k in range(seg)))
    return new_obj(name, verts, faces, colname)


def ribbon(name, pts, widths, thickness, seg=24, colname="Maid",
           normal_hint=(0, -1, 0), taper=None):
    """Flat ribbon strip along pts with real thickness (closed shell)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    if callable(widths):
        W = [widths(i / (n - 1)) for i in range(n)]
    elif isinstance(widths, (list, tuple)):
        W = list(widths)
    else:
        W = [widths] * n
    hint = Vector(normal_hint).normalized()
    tangents = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            t = P[i + 1] - P[i - 1]
        tangents.append(t.normalized())
    verts = []
    half = thickness * 0.5
    for side in (-1, 1):
        for i in range(n):
            t = tangents[i]
            nv = hint - t * hint.dot(t)
            if nv.length < 1e-6:
                nv = Vector((1, 0, 0))
            nv.normalize()
            bn = t.cross(nv).normalized()
            verts.append(tuple(P[i] + nv * (half * side) - bn * W[i]))
            verts.append(tuple(P[i] + nv * (half * side) + bn * W[i]))
    # each side layer: 2 verts per point (left,right)
    faces = []
    base2 = n * 2
    for layer in (0, 1):
        off = layer * base2
        for i in range(n - 1):
            a = off + i * 2
            b = off + i * 2 + 1
            c = off + (i + 1) * 2 + 1
            d = off + (i + 1) * 2
            faces.append((a, b, c, d))
    # side walls
    for i in range(n - 1):
        # left edge
        faces.append((i * 2, (i + 1) * 2, base2 + (i + 1) * 2, base2 + i * 2))
        # right edge
        faces.append((i * 2 + 1, base2 + i * 2 + 1, base2 + (i + 1) * 2 + 1, (i + 1) * 2 + 1))
    # end caps
    faces.append((0, base2, base2 + 1, 1))
    e = (n - 1) * 2
    faces.append((e, e + 1, base2 + e + 1, base2 + e))
    ob = new_obj(name, verts, faces, colname)
    recalc_normals(ob)
    return ob


def disc(name, radius, seg=64, rings=12, center=(0, 0, 0), z=0.0,
         fn=None, colname="Maid"):
    """Flat disc in the XZ plane at y=const, subdivided radially (for eye parts)."""
    c = Vector(center)
    verts = [tuple(c)]
    for j in range(1, rings + 1):
        r = radius * j / rings
        for i in range(seg):
            a = TAU * i / seg
            p = Vector((c.x + r * cos(a), c.y, c.z + r * sin(a)))
            if fn:
                p = fn(p, r / radius, a)
            verts.append(tuple(p))
    faces = []
    for i in range(seg):
        i2 = (i + 1) % seg
        faces.append((0, 1 + i, 1 + i2))
    for j in range(rings - 1):
        b0 = 1 + j * seg
        b1 = 1 + (j + 1) * seg
        for i in range(seg):
            i2 = (i + 1) % seg
            faces.append((b0 + i, b1 + i, b1 + i2, b0 + i2))
    return new_obj(name, verts, faces, colname)


# ---------------------------------------------------------------- deformers
def deform(ob, fn):
    me = ob.data
    for v in me.vertices:
        v.co = Vector(fn(Vector(v.co)))
    me.update()


def gauss_bump(ob, center, sigma, amp, direction=None):
    c = Vector(center)
    me = ob.data
    for v in me.vertices:
        d = (v.co - c).length
        f = exp(-(d / sigma) ** 2)
        if f < 1e-4:
            continue
        nv = v.normal if direction is None else Vector(direction)
        v.co = v.co + nv * (amp * f)
    me.update()


def gauss_bump_scalar(ob, center, sigma, amp, axis=2):
    c = Vector(center)
    me = ob.data
    for v in me.vertices:
        d = (v.co - c).length
        f = exp(-((d / sigma) ** 2))
        if f < 1e-4:
            continue
        co = v.co.copy()
        co[axis] += amp * f
        v.co = co
    me.update()


def smooth_verts(ob, iterations=2, factor=0.5):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for _ in range(iterations):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=factor,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(me)
    bm.free()
    me.update()


# ---------------------------------------------------------------- modifiers
def add_subsurf(ob, levels=1, render=None, apply=False):
    m = ob.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels if render is None else render
    m.use_limit_surface = False
    if apply:
        apply_mods(ob)
    return m


def add_solidify(ob, thickness, offset=-1.0, apply=True, even=True, rim=True):
    m = ob.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = even
    m.use_rim = rim
    m.use_quality_normals = True
    if apply:
        apply_mods(ob)
    return m


def add_bevel(ob, width, segments=2, angle=0.6, apply=True, clamp=True):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = angle
    m.use_clamp_overlap = clamp
    if apply:
        apply_mods(ob)
    return m


def apply_mods(ob):
    prev = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except Exception as e:
            print("modifier apply failed", ob.name, m.name, e)
    bpy.context.view_layer.objects.active = prev


def shade_smooth(ob, angle_deg=None):
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    if angle_deg is not None:
        prev = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = ob
        try:
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))
        except Exception:
            pass
        finally:
            bpy.context.view_layer.objects.active = prev


def join_objs(objs, name=None):
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    if name:
        ob.name = name
        ob.data.name = name
    return ob


def mirror_x(ob, name=None):
    """Duplicate and mirror across X (keeps normals outward)."""
    new = ob.copy()
    new.data = ob.data.copy()
    get_collection("Maid").objects.link(new)
    new.name = name or (ob.name + "_mir")
    new.scale = (-ob.scale.x, ob.scale.y, ob.scale.z)
    bpy.context.view_layer.objects.active = new
    bpy.ops.object.select_all(action="DESELECT")
    new.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    recalc_normals(new)
    return new


def apply_scale_rot(ob):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


# ---------------------------------------------------------------- materials
def _set(node, name, val):
    if name in node.inputs:
        try:
            node.inputs[name].default_value = val
        except Exception:
            pass


def material(name, color, rough=0.45, metal=0.0, spec=0.5, sss=0.0,
             sss_radius=(0.9, 0.35, 0.2), sss_scale=0.02, coat=0.0,
             coat_rough=0.06, sheen=0.0, emit=None, emit_str=0.0,
             alpha=1.0, aniso=0.0, ior=1.45):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    _set(bsdf, "Base Color", color)
    _set(bsdf, "Roughness", rough)
    _set(bsdf, "Metallic", metal)
    _set(bsdf, "Specular IOR Level", spec)
    _set(bsdf, "IOR", ior)
    _set(bsdf, "Alpha", alpha)
    _set(bsdf, "Subsurface Weight", sss)
    _set(bsdf, "Subsurface Radius", sss_radius)
    _set(bsdf, "Subsurface Scale", sss_scale)
    _set(bsdf, "Coat Weight", coat)
    _set(bsdf, "Coat Roughness", coat_rough)
    _set(bsdf, "Sheen Weight", sheen)
    _set(bsdf, "Anisotropic", aniso)
    if emit is not None:
        _set(bsdf, "Emission Color", emit)
        _set(bsdf, "Emission Strength", emit_str)
    if alpha < 1.0:
        m.blend_method = "BLEND"
    m.diffuse_color = color
    return m


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def assign_multi(ob, mats):
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)


def set_face_material(ob, face_indices, slot):
    for i in face_indices:
        ob.data.polygons[i].material_index = slot


# ---------------------------------------------------------------- render setup
def set_engine(name="EEVEE"):
    scene = bpy.context.scene
    for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = cand
            return cand
        except Exception:
            continue
    return scene.render.engine


def setup_render(res=(900, 1200), samples=48, transparent=False):
    s = bpy.context.scene
    set_engine()
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.film_transparent = transparent
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    eev = getattr(s, "eevee", None)
    if eev:
        for attr, val in (("taa_render_samples", samples), ("use_gtao", True),
                          ("use_raytracing", True), ("use_shadows", True),
                          ("use_volumetric_lights", False)):
            if hasattr(eev, attr):
                try:
                    setattr(eev, attr, val)
                except Exception:
                    pass
    s.view_settings.view_transform = "Standard"
    s.view_settings.look = "None"
    s.render.fps = 24


def add_camera(name, loc, target, lens=85, ortho=None, colname="Maid"):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    cam = bpy.data.objects.new(name, cam_data)
    get_collection(colname).objects.link(cam)
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return cam


def add_area_light(name, loc, target, energy=100.0, size=1.0, color=(1, 1, 1),
                   shape="DISK", colname="Maid"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.shape = shape
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    get_collection(colname).objects.link(ob)
    ob.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def render_to(path, cam=None):
    s = bpy.context.scene
    if cam is not None:
        s.camera = cam
    s.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path
