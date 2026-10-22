# =============================================================================
# ruffle.py -- procedural scalloped ruffle / frill bands for Blender
# =============================================================================
"""Procedural scalloped ruffle (frill / gathered lace trim) generator.

Pure ``bpy`` + ``mathutils`` (no external dependencies).  Works with Blender
4.2 LTS .. 5.x.

Public API
----------
    build_ruffle(name="ruffle", path=None, up=(0,0,1), width=0.020,
                 scallops=None, amp=0.006, pleat=0.0015, thickness=0.0022,
                 flare=0.35, closed=None, style="scallop", start_angle=0.0)
        -> bpy.types.Object

What it builds
--------------
A strip of fabric that follows ``path`` (the seam / attachment line, world
space).  At every path point the strip extends horizontally outward along

    d(u) = normalize( P(u) - centroid(P) ,  projected perpendicular to up )

by a radial amount ``R(u) = width + amp * shape(u)``, and its outer edge is
lifted along ``up`` by ``flare * width * shape2(u)``.  ``shape`` is a run of
semicircular arcs standing on the base circle, so neighbouring lobes meet in
the classic inward cusp; ``shape2`` makes each lobe pouch upward more than the
cusps, which is what makes it read as gathered cloth instead of a flat
cut-out.

The strip is a real closed shell: a cross-section loop (front face -> rounded
outer rim -> back face -> rounded inner rim) is swept along the path, so the
result is watertight, has applied thickness, and a soft rounded rim (plus a
small angle-limited Bevel, then a level-1 Subdivision Surface, both applied).

Construction details
--------------------
* the input path is first densified with a *centripetal* Catmull-Rom spline
  (so 3 points are enough) and then re-sampled at uniform arc length, so a
  non-uniform loop still gets exactly ``scallops`` equally wide lobes;
* closed / open is auto-detected from the endpoint gap (or forced);
* open paths are capped at both ends;
* object origin stays at the world origin, vertices are world space.

Example
-------
    import ruffle
    import math
    path = [(0.10*math.cos(a), 0.10*math.sin(a), 0.0)
            for a in [i*2*math.pi/64 for i in range(64)]]
    ob = ruffle.build_ruffle("apron_hem", path, width=0.022,
                             amp=0.007, flare=0.30, scallops=15)
"""

import math

import bpy
import bmesh
from mathutils import Vector

__all__ = ["build_ruffle"]

_TAU = 2.0 * math.pi

# resolution defaults (spec: >= 8 subdivisions across the width,
# >= 10 samples per lobe)
_ACROSS = 9          # segments across the frill width
_RIM_SEG = 3         # segments in each rounded rim (180 deg)
_PER_LOBE = 16       # path segments per scallop lobe
_PER_SEG = 32        # dense samples per input control-point span


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _v3(p):
    """Coerce a 3-tuple / Vector into a Vector, with a useful error."""
    try:
        return Vector((float(p[0]), float(p[1]), float(p[2])))
    except (TypeError, IndexError, ValueError) as exc:
        raise ValueError("path entries must be 3-tuples / mathutils.Vector") from exc


def _clean_path(pts):
    """Drop consecutive duplicates (eps is 0.1 micron -- cloth scale safe)."""
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > 1e-7:
            out.append(p)
    return out


def _polyline_length(pts, closed):
    total = 0.0
    n = len(pts)
    for i in range(n if closed else n - 1):
        total += (pts[(i + 1) % n] - pts[i]).length
    return total


def _auto_closed(pts):
    """Heuristic: a uniformly sampled loop has an endpoint gap of one step."""
    n = len(pts)
    if n < 4:
        return False
    gap = (pts[-1] - pts[0]).length
    step = _polyline_length(pts, False) / float(n - 1)
    if step <= 1e-12:
        return True
    return gap <= 1.6 * step


def _cr(p0, p1, p2, p3, t):
    """Centripetal Catmull-Rom (Barry-Goldman), t in [0,1] on p1..p2."""
    def knot(ti, a, b):
        d = (b - a).length
        return ti + max(d, 1e-9) ** 0.5

    t0 = 0.0
    t1 = knot(t0, p0, p1)
    t2 = knot(t1, p1, p2)
    t3 = knot(t2, p2, p3)
    tt = t1 + (t2 - t1) * t
    a1 = ((t1 - tt) * p0 + (tt - t0) * p1) / (t1 - t0)
    a2 = ((t2 - tt) * p1 + (tt - t1) * p2) / (t2 - t1)
    a3 = ((t3 - tt) * p2 + (tt - t2) * p3) / (t3 - t2)
    b1 = ((t2 - tt) * a1 + (tt - t0) * a2) / (t2 - t0)
    b2 = ((t3 - tt) * a2 + (tt - t1) * a3) / (t3 - t1)
    return ((t2 - tt) * b1 + (tt - t1) * b2) / (t2 - t1)


def _densify(pts, closed, per_seg=_PER_SEG):
    """Catmull-Rom densify the control polygon (endpoints reflected if open)."""
    n = len(pts)
    if n < 2:
        raise ValueError("path needs at least 2 points")
    if n == 2:
        return [pts[0].lerp(pts[1], i / float(per_seg)) for i in range(per_seg + 1)]

    out = []
    segs = n if closed else n - 1
    for i in range(segs):
        i0 = (i - 1) % n if closed else max(i - 1, 0)
        i1 = i % n
        i2 = (i + 1) % n
        i3 = (i + 2) % n if closed else min(i + 2, n - 1)
        p0, p1, p2, p3 = pts[i0], pts[i1], pts[i2], pts[i3]
        if not closed:
            if i0 == i1:                      # start: reflect the end tangent
                p0 = p1 + (p1 - p2)
            if i3 == i2:                      # end: reflect
                p3 = p2 + (p2 - p1)
        for k in range(per_seg):
            out.append(_cr(p0, p1, p2, p3, k / float(per_seg)))
    if not closed:
        out.append(pts[-1])
    return out


def _resample(dense, closed, count, total):
    """Uniform arc-length resampling of a dense polyline."""
    m = len(dense)
    if m < 2:
        raise ValueError("degenerate path")
    seg_n = m if closed else m - 1
    starts = [0.0] * seg_n
    lens = [0.0] * seg_n
    acc = 0.0
    for i in range(seg_n):
        starts[i] = acc
        lens[i] = (dense[(i + 1) % m] - dense[i]).length
        acc += lens[i]
    if total <= 1e-12:
        raise ValueError("path has zero length")

    out = []
    j = 0
    denom = float(count) if closed else float(max(1, count - 1))
    for k in range(count):
        s = total * (k / denom)
        while j < seg_n - 1 and s > starts[j] + lens[j]:
            j += 1
        t = 0.0 if lens[j] <= 1e-15 else (s - starts[j]) / lens[j]
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        out.append(dense[j].lerp(dense[(j + 1) % m], t))
    return out


def _lobe_values(style, ph):
    """Return (radial shape in [0,1], lift shape in [0,1]) for phase `ph`.

    The scallop is the classic construction: the outer boundary is a run of
    *semicircular arcs* standing on the base circle, so two neighbouring lobes
    meet in a true inward cusp (vertical tangents) -- that is what gives a
    lace trim its bite.  The arc also sets how the lobe pouches up
    (`shape2`), smoothly and in phase with the arc.
    """
    x = (ph / _TAU) % 1.0          # 0..1 inside one lobe
    if style == "zigzag":
        tri = 1.0 - abs(2.0 * x - 1.0)
        return tri, 0.15 + 0.85 * tri
    # |sin|: round lobes that meet under a *finite* cusp angle.  (An exponent
    # < 1 -- or a semicircle -- gives a vertical tangent at the cusp, and with
    # any flare that reads as sheet-metal tabs rather than cloth.)
    s = abs(math.sin(math.pi * x))
    return s, 0.18 + 0.82 * s


def _apply_modifiers(obj):
    """Bake the modifier stack into the object's mesh (no bpy.ops needed)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    new_me = bpy.data.meshes.new_from_object(ev, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_me
    new_me.name = (obj.name + "_mesh")[:60]
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return new_me


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def build_ruffle(name="ruffle", path=None, up=(0.0, 0.0, 1.0),
                 width=0.020, scallops=None, amp=0.006, pleat=0.0015,
                 thickness=0.0022, flare=0.35, closed=None,
                 style="scallop", start_angle=0.0):
    """Build one scalloped ruffle band around `path` and return its object.

    path       : ordered 3-tuples / Vectors in WORLD space -- the seam line.
    up         : frill "up" axis (the frill lies in the plane perpendicular
                 to it and cups along it).  Need not be normalised.
    width      : radial extent of the frill from the attach line (m).
    scallops   : exact number of lobes along the whole path, or None to
                 derive it from the path length (target lobe width
                 ~ width * 1.15).
    amp        : scallop amplitude -- the outer edge bulges +amp at lobe
                 centres and comes back to `width` at the cusps (m).
    pleat      : small up/down ripple (fabric gather), grows toward the
                 outer edge (m).
    thickness  : fabric thickness (m).
    flare      : 0 = flat, 1 = strongly cupped; outer edge rises by
                 `flare * width * shape2(u)`.
    closed     : True/False to force, None to auto-detect.
    style      : "scallop" (rounded lobes, cusped) or "zigzag" (sharp).
    start_angle: rotates the lobe pattern along the path (radians, one full
                 lobe = 2*pi).
    """
    # ---- validate ---------------------------------------------------------
    if path is None:
        raise ValueError("build_ruffle(): 'path' is required")
    width = float(width)
    if width <= 0.0:
        raise ValueError("width must be > 0")
    thickness = float(thickness)
    if thickness <= 0.0:
        raise ValueError("thickness must be > 0")
    amp = max(0.0, float(amp))
    flare = float(flare)
    pleat = float(pleat)
    style = str(style).strip().lower()
    if style not in ("scallop", "zigzag"):
        raise ValueError("style must be 'scallop' or 'zigzag'")

    upv = Vector(up)
    if upv.length < 1e-9:
        raise ValueError("up must be a non-zero vector")
    upv = upv.normalized()

    pts = _clean_path([_v3(p) for p in path])
    if len(pts) < 3:
        raise ValueError("path needs at least 3 distinct points")

    if closed is None:
        closed = _auto_closed(pts)
    else:
        closed = bool(closed)
    if closed and (pts[-1] - pts[0]).length < 1e-6:
        pts = pts[:-1]                      # duplicated closing point
        if len(pts) < 3:
            raise ValueError("closed path needs at least 3 distinct points")

    # ---- resample by arc length ------------------------------------------
    dense = _densify(pts, closed)
    total = _polyline_length(dense, closed)
    if total <= 1e-9:
        raise ValueError("path has zero length")

    if scallops is None:
        scallops = max(2, int(round(total / max(width * 1.15, 1e-9))))
    try:
        scallops = int(scallops)
    except (TypeError, ValueError) as exc:
        raise ValueError("scallops must be an int or None") from exc
    if scallops < 1:
        raise ValueError("scallops must be >= 1")

    nseg = max(48, min(scallops * _PER_LOBE, 4096))
    nring = nseg if closed else nseg + 1
    pos = _resample(dense, closed, nring, total)

    # ---- outward (radial) direction per ring ------------------------------
    centroid = Vector((0.0, 0.0, 0.0))
    for p in pos:
        centroid += p
    centroid /= float(nring)

    radial = []
    prev = None
    for i, P in enumerate(pos):
        w = P - centroid
        w = w - upv * w.dot(upv)
        if w.length > 1e-7:
            d = w.normalized()
        else:
            # degenerate (point sits on the centroid axis): use the curve
            # normal and keep it continuous with the previous ring
            a = pos[(i - 1) % nring]
            b = pos[(i + 1) % nring]
            t = b - a
            if t.length < 1e-12:
                t = Vector((1.0, 0.0, 0.0))
            d = t.cross(upv)
            if d.length < 1e-12:
                d = Vector((1.0, 0.0, 0.0))
            d.normalize()
            if prev is not None and d.dot(prev) < 0.0:
                d = -d
        radial.append(d)
        prev = d

    # ---- horizontal path tangents (for the pleat lean) --------------------
    tangent = []
    for i in range(nring):
        if closed:
            a, b = pos[(i - 1) % nring], pos[(i + 1) % nring]
        else:
            a = pos[max(i - 1, 0)]
            b = pos[min(i + 1, nring - 1)]
        t = b - a
        t = t - upv * t.dot(upv)          # keep the lean inside the frill plane
        if t.length < 1e-12:
            t = upv.cross(Vector((0.0, 0.0, 1.0)))
            if t.length < 1e-12:
                t = Vector((1.0, 0.0, 0.0))
        tangent.append(t.normalized())

    # ---- sweep the closed cross-section ----------------------------------
    th2 = 0.5 * thickness
    k_pleat = max(3, int(round(2.0 * scallops)))
    k_pleat2 = max(3, int(round(1.35 * scallops)))
    k_slow = max(1, int(round(0.25 * scallops)))
    lean_amp = min(pleat / max(width, 1e-9), 0.35)
    loop_n = 2 * (_ACROSS + 1) + 2 * (_RIM_SEG - 1)

    verts = []
    for i in range(nring):
        u = i / float(nseg)
        shape, shape2 = _lobe_values(style, _TAU * scallops * u + start_angle)
        # a few percent of lobe-to-lobe variation: hand-gathered cloth is
        # never stamped identical, and perfectly equal lobes read as plastic.
        # (integer frequency, so a closed loop stays seamless)
        amp_j = amp * (1.0 + 0.07 * math.sin(_TAU * 3.0 * u + 1.3))

        R = max(width + amp_j * shape, width * 0.12)
        H = flare * width * shape2

        # gather: two incommensurate ripples, slowly modulated so it never
        # looks corrugated, and tapered before the rim so the scalloped edge
        # stays a clean read instead of a saw blade
        ph1 = _TAU * k_pleat * u + start_angle
        ph2 = _TAU * k_pleat2 * u + 0.5 * start_angle
        env = 0.58 + 0.42 * math.sin(_TAU * k_slow * u + 2.1)
        pl = pleat * env * (0.65 * math.sin(ph1) + 0.35 * math.sin(ph2 + 1.2))
        lean = lean_amp * env * (0.72 * math.sin(ph1 + 1.5708)
                                 + 0.28 * math.sin(ph2 + 0.35))

        P = pos[i]
        d = radial[i]
        if abs(lean) > 1e-6:
            d = (d * math.cos(lean) + tangent[i] * math.sin(lean)).normalized()

        # mid-surface cross-section in the (radial, up) plane.
        #   H*t^1.7  = the cup / curl of the free edge
        #   puff     = the lobe billows in the middle of the band (excess cloth
        #              a gathered frill has); zero at the cusps, so the cusps
        #              stay pinched and the band does not read as flat card
        puff = 0.40 * amp_j * shape
        p2 = []
        for j in range(_ACROSS + 1):
            t = j / float(_ACROSS)
            # gather ripple lives in the body of the band and only whispers
            # at the free edge, so the scalloped silhouette stays crisp
            w = (t ** 1.1) * (0.35 + 0.65 * math.sin(math.pi * t) ** 0.7)
            p2.append(Vector((R * t,
                              H * (t ** 1.7)
                              + puff * math.sin(math.pi * t) ** 1.15
                              + pl * w)))

        # in-plane normals (always pointing toward +up)
        n2 = []
        for j in range(_ACROSS + 1):
            if j == 0:
                tv = p2[1] - p2[0]
            elif j == _ACROSS:
                tv = p2[-1] - p2[-2]
            else:
                tv = p2[j + 1] - p2[j - 1]
            if tv.length < 1e-12:
                tv = Vector((1.0, 0.0))
            tv.normalize()
            nv = Vector((-tv.y, tv.x))
            if nv.y < 0.0:
                nv = -nv
            n2.append(nv)

        def to3(q, nvec, off):
            return (P + d * q.x + upv * q.y
                    + (d * nvec.x + upv * nvec.y) * off)

        ring = []
        # front surface, seam -> outer edge
        for j in range(_ACROSS + 1):
            ring.append(to3(p2[j], n2[j], th2))
        # rounded outer rim (front -> back, bulging outward)
        t_end = (p2[-1] - p2[-2]).normalized()
        for j in range(1, _RIM_SEG):
            a = math.pi * j / _RIM_SEG
            q = p2[-1] + (n2[-1] * math.cos(a) + t_end * math.sin(a)) * th2
            ring.append(to3(q, n2[-1], 0.0))
        # back surface, outer edge -> seam
        for j in range(_ACROSS, -1, -1):
            ring.append(to3(p2[j], n2[j], -th2))
        # rounded inner rim (back -> front, bulging inward)
        t0 = (p2[1] - p2[0]).normalized()
        for j in range(1, _RIM_SEG):
            a = math.pi * j / _RIM_SEG
            q = p2[0] + (-n2[0] * math.cos(a) - t0 * math.sin(a)) * th2
            ring.append(to3(q, n2[0], 0.0))

        verts.extend(ring)
    # ---- faces ------------------------------------------------------------
    faces = []
    n_conn = nring if closed else nring - 1
    for i in range(n_conn):
        a = i * loop_n
        b = ((i + 1) % nring) * loop_n
        for k in range(loop_n):
            k2 = (k + 1) % loop_n
            faces.append((a + k, a + k2, b + k2, b + k))
    if not closed:
        faces.append(tuple(range(loop_n - 1, -1, -1)))
        base = (nring - 1) * loop_n
        faces.append(tuple(base + k for k in range(loop_n)))

    # ---- mesh / object ----------------------------------------------------
    me = bpy.data.meshes.new(name + "_mesh")
    me.from_pydata([v[:] for v in verts], [], faces)
    me.validate(verbose=False)
    me.update()

    obj = bpy.data.objects.new(name, me)
    scene = bpy.context.scene
    scene.collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)

    # consistent outward normals
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()

    # ---- soften + subdivide, then bake -----------------------------------
    bev = obj.modifiers.new("RuffleBevel", 'BEVEL')
    bev.limit_method = 'ANGLE'
    bev.angle_limit = math.radians(65.0)     # only the flat end caps
    bev.width = min(0.35 * thickness, 0.20 * width)
    bev.segments = 2
    bev.use_clamp_overlap = True

    sub = obj.modifiers.new("RuffleSubdiv", 'SUBSURF')
    sub.levels = 1
    sub.render_levels = 1
    sub.use_limit_surface = True

    final = _apply_modifiers(obj)
    for poly in final.polygons:
        poly.use_smooth = True
    final.update()

    return obj
