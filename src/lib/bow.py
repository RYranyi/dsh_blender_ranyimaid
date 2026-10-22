# -*- coding: utf-8 -*-
"""Procedural satin ribbon bow -- the back-waist bow of a maid dress.

Everything is generated from scratch with pure ``bpy``/``mathutils`` maths: no
assets, no modifiers, no textures, fully deterministic.  ``build_bow()`` returns
one joined mesh object.

Layout (local space, knot at the origin)
----------------------------------------
* loops spread along ``+-X``, tips droop by ``droop`` radians below horizontal
* tails hang towards ``-Z``
* the ribbon faces point mostly towards ``-Y`` (the viewer / character back)

How the ribbon is folded
------------------------
Each loop is one ribbon strip that leaves the knot, travels outwards along the
loop's upper (or lower) arm, folds back on itself at the outer tip over a
generous round fold and comes back to the knot.  The two arms are separated by
``s = loop_h - ribbon_w`` along the loop's normal, therefore the loop's
silhouette is exactly ``s + ribbon_w == loop_h``.  The strip's width tapers into
the knot (the pinch) and the cross section *rolls* by ``loop_twist`` as it
approaches the pinch, so the fold is clean but the loop reads three dimensional.

The strip itself is swept as a closed lens:  thickness is real geometry (a
``thickness``-thick lens whose faces crown slightly and whose long edges are
rounded), sampled 16 times around the section (9 samples across each face) and
60 times along each loop.

Tails are swept S-curves, offset in depth from each other so they never z-fight,
emerging from *behind* the loops, with an angled V-notched cut end.
"""

import math

import bpy
import bmesh
from mathutils import Vector

__all__ = ["build_bow"]

_TAU = math.pi * 2.0


# ---------------------------------------------------------------------------
# small maths helpers
# ---------------------------------------------------------------------------
def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def _smoothstep(e0, e1, x):
    if e1 == e0:
        return 0.0 if x < e0 else 1.0
    t = _clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _lens_profile(m=20):
    """Closed (across, half-thickness) profile of the ribbon's cross section.

    ``across`` runs -1..1 (scaled by the strip's half width), the second value is
    a 0..1 factor scaled by the half thickness.  The face stays almost flat out
    to ~80% of the width and then rolls over into a fully round long edge, which
    reads as a satin ribbon rather than a tube; the samples are cosine spaced so
    that rolled edge gets plenty of vertices.
    """
    m = max(8, int(round(m)))
    n_half = m // 2 + 1
    top = []
    for k in range(n_half):
        v = -math.cos(math.pi * k / (n_half - 1.0))
        h = math.sqrt(max(0.0, 1.0 - abs(v) ** 4.5))
        top.append((v, h))
    pts = list(top)                                  # -1 .. +1
    for k in range(n_half - 2, 0, -1):               # +1 .. -1 (edges shared)
        v, h = top[k]
        pts.append((v, -h))
    return pts


def _frame(tangent, ref, psi):
    """Ribbon frame: width axis W, face normal Nn, rolled by ``psi`` about T."""
    w0 = ref.cross(tangent)
    if w0.length_squared < 1e-18:
        w0 = Vector((0.0, 0.0, 1.0))
    w0.normalize()
    n0 = tangent.cross(w0)
    n0.normalize()
    if psi:
        c, s = math.cos(psi), math.sin(psi)
        return w0 * c + n0 * s, n0 * c - w0 * s
    return w0, n0


def _tangents(pts):
    out = []
    last = len(pts) - 1
    for i in range(len(pts)):
        i0 = max(0, i - 1)
        i1 = min(last, i + 1)
        t = pts[i1] - pts[i0]
        if t.length_squared < 1e-18:
            t = Vector((0.0, 0.0, 1.0))
        out.append(t.normalized())
    return out


def _section_points(base, w_axis, n_axis, half_w, half_t, crown, profile):
    """One closed cross-section ring around ``base``."""
    pts = []
    for v, h in profile:
        off = half_t * h + crown * (1.0 - v * v)
        pts.append(base + w_axis * (half_w * v) + n_axis * off)
    return pts


# ---------------------------------------------------------------------------
# mesh accumulator
# ---------------------------------------------------------------------------
class _Builder(object):
    __slots__ = ("verts", "faces", "sharp")

    def __init__(self):
        self.verts = []
        self.faces = []
        self.sharp = set()

    def vert(self, co):
        self.verts.append((float(co[0]), float(co[1]), float(co[2])))
        return len(self.verts) - 1

    def ring(self, points):
        return [self.vert(p) for p in points]

    def face(self, idx):
        if len(idx) >= 3:
            self.faces.append(tuple(idx))

    def bridge(self, ra, rb):
        m = len(ra)
        for i in range(m):
            j = (i + 1) % m
            self.face((ra[i], ra[j], rb[j], rb[i]))

    def cap(self, ring):
        """Close a ring with a triangle fan; its rim is marked sharp (a cut)."""
        if len(ring) < 3:
            return
        cx = cy = cz = 0.0
        for i in ring:
            x, y, z = self.verts[i]
            cx += x
            cy += y
            cz += z
        inv = 1.0 / float(len(ring))
        ci = self.vert((cx * inv, cy * inv, cz * inv))
        m = len(ring)
        for i in range(m):
            j = (i + 1) % m
            self.face((ring[i], ring[j], ci))
            a, b = ring[i], ring[j]
            self.sharp.add((a, b) if a < b else (b, a))


# ---------------------------------------------------------------------------
# ribbon parts
# ---------------------------------------------------------------------------
def _add_loop(sb, sign, width, loop_h, ribbon_w, thickness, droop, twist,
              profile, samples, crown, y_off=0.0):
    """One folded ribbon loop (out from the knot, around the tip, back)."""
    half_t = thickness * 0.5

    # arm separation -> silhouette height == loop_h; never let the two arms
    # cross over each other (that would self-intersect at the loop's waist).
    b = max((loop_h - ribbon_w) * 0.5, ribbon_w * 0.52)
    # the folded band's own half width is what reaches +-width/2
    a = max((width - ribbon_w) * 0.25 / max(0.2, math.cos(droop)), 1e-5)

    d = Vector((sign * math.cos(droop), 0.0, -math.sin(droop)))
    n = Vector((sign * math.sin(droop), 0.0, math.cos(droop)))
    center = d * a
    cup = ribbon_w * 0.42                      # tip lifts off the body
    ref = Vector((0.0, -1.0, 0.0))
    # slightly super-elliptic loop: straighter arms, tighter throat and tip
    e = 2.15
    k = 2.0 / e

    us = [i / (samples - 1.0) for i in range(samples)]
    pts = []
    for u in us:
        phi = math.pi + _TAU * u               # pi -> knot, 2pi -> tip
        cp = math.cos(phi)
        sp = math.sin(phi)
        ex = math.copysign(abs(cp) ** k, cp)
        ez = math.copysign(abs(sp) ** k, sp)
        p = center + d * (a * ex) + n * (b * ez)
        p.y += (-cup * math.sin(math.pi * u) ** 2.0
                + y_off + 0.0012 * (1.0 - u))
        pts.append(p)
    tans = _tangents(pts)

    rings = []
    for i, u in enumerate(us):
        taper = _smoothstep(0.0, 0.10, u) * _smoothstep(0.0, 0.10, 1.0 - u)
        wid = ribbon_w * (0.12 + 0.88 * taper)
        q = abs(2.0 * u - 1.0)                 # 0 at the fold, 1 at the pinch
        psi = twist * (0.30 + 0.70 * _smoothstep(0.12, 1.0, q))
        w_ax, n_ax = _frame(tans[i], ref, psi)
        rings.append(sb.ring(
            _section_points(pts[i], w_ax, n_ax, wid * 0.5, half_t, crown, profile)))

    for i in range(len(rings) - 1):
        sb.bridge(rings[i], rings[i + 1])
    sb.cap(rings[0])
    sb.cap(rings[-1])


def _add_tail(sb, seat, y0, tail_len, tail_spread, ribbon_w, thickness,
              notch, profile, samples, crown, twist=0.22):
    """One hanging ribbon tail with a gentle S-curve and a V-notched cut end."""
    half_t = thickness * 0.5
    half_spread = max(tail_spread * 0.5, 0.0)
    outward = 1.0 if seat > 0 else (-1.0 if seat < 0 else 0.0)
    start_x = 0.0085 * outward
    ref = Vector((0.0, -1.0, 0.0))

    def path(s):
        grow = 0.08 * s + 0.92 * s ** 2.0
        x = seat * (abs(start_x) + max(half_spread - abs(start_x), 0.0) * grow)
        x -= seat * 0.0035 * math.sin(math.pi * s)          # the S
        z = 0.004 - tail_len * s
        y = y0 - 0.0040 * s ** 1.6
        return Vector((x, y, z))

    ss = [i / (samples - 1.0) for i in range(samples)]
    pts = [path(s) for s in ss]
    tans = _tangents(pts)

    rings = []
    for i, s in enumerate(ss):
        wid = ribbon_w * (1.0 + 0.04 * s)
        psi = twist * s
        w_ax, n_ax = _frame(tans[i], ref, psi)
        rings.append(sb.ring(
            _section_points(pts[i], w_ax, n_ax, wid * 0.5, half_t, crown, profile)))

    # cut the free end: shallow V bite, tilted so the outer corner hangs longer
    t_end = tans[-1]
    bite = 0.75 * notch
    tilt = 0.85 * notch
    last_w, last_n = _frame(t_end, ref, twist)
    last_pts = _section_points(pts[-1], last_w, last_n,
                               ribbon_w * 1.04 * 0.5, half_t, crown, profile)
    end_pts = []
    for (v, _h), p in zip(profile, last_pts):
        delta = bite * (1.0 - abs(v) ** 2.4) - tilt * (v * outward)
        end_pts.append(p - t_end * delta)
    rings[-1] = sb.ring(end_pts)

    for i in range(len(rings) - 1):
        sb.bridge(rings[i], rings[i + 1])
    sb.cap(rings[0])
    sb.cap(rings[-1])


def _add_knot(sb, knot_w, knot_h, ribbon_w, y_front, y_back, samples=19, m=28):
    """The pinched wrap band: a rounded slab with a crease across its front."""
    hx = knot_w * 0.5
    hz = knot_h * 0.5
    e = 3.2                                   # superellipse -> soft rectangle
    groove = 0.085 * knot_h                   # crease depth
    z_crease = 0.10                           # slightly above the middle
    y_mid = (y_front + y_back) * 0.5
    rings = []
    for j in range(samples):
        t = j / (samples - 1.0)
        y = y_front + (y_back - y_front) * t
        u = 2.0 * t - 1.0
        aa = abs(u)
        if aa <= 0.78:                        # flat band, rounded edges
            scale = 1.0
        else:
            q = (aa - 0.78) / 0.22
            scale = max(0.06, math.sqrt(max(0.0, 1.0 - q * q)))
        front = max(0.0, 1.0 - 1.9 * t)       # the crease lives on the front
        pts = []
        for k in range(m):
            th = _TAU * k / m
            cx = math.cos(th)
            cz = math.sin(th)
            ex = math.copysign(abs(cx) ** (2.0 / e), cx)
            ez = math.copysign(abs(cz) ** (2.0 / e), cz)
            g = math.exp(-(((ez - z_crease) / 0.20) ** 2)) * front
            xx = ex * hx * scale * (1.0 - 0.030 * g)
            zz = ez * hz * scale
            # the band hugs the ribbon bundle: thinner towards its top / bottom
            hug = 1.0 - 0.45 * ez * ez
            yy = y_mid + (y - y_mid + groove * g) * hug
            pts.append(Vector((xx, yy, zz)))
        rings.append(sb.ring(pts))
    for i in range(len(rings) - 1):
        sb.bridge(rings[i], rings[i + 1])
    sb.cap(rings[0])
    sb.cap(rings[-1])


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def _to_object(sb, name, location, rotation):
    me = bpy.data.meshes.new(name)
    me.from_pydata(sb.verts, [], sb.faces)
    me.validate(verbose=False)
    me.update(calc_edges=True)

    # consistent, outward facing normals for every closed shell
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()

    for poly in me.polygons:
        poly.use_smooth = True

    if sb.sharp:
        lookup = {}
        for i, edge in enumerate(me.edges):
            a, b = edge.vertices
            lookup[(a, b) if a < b else (b, a)] = i
        try:
            for key in sb.sharp:
                idx = lookup.get(key)
                if idx is not None:
                    me.edges[idx].use_edge_sharp = True
        except Exception:                     # pragma: no cover - API fallback
            pass
    me.update()

    ob = bpy.data.objects.new(name, me)
    ob.location = location
    ob.rotation_euler = rotation
    coll = None
    try:
        coll = bpy.context.collection
    except Exception:
        coll = None
    if coll is None:
        coll = bpy.context.scene.collection
    coll.objects.link(ob)
    return ob


def build_bow(name="bow", location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
              width=0.115, loop_h=0.062, ribbon_w=0.020, thickness=0.0018,
              tails=2, tail_len=0.115, tail_spread=0.055, tail_notch=0.008,
              loop_twist=0.55, droop=0.28,
              knot=True, knot_w=0.020, knot_h=0.024):
    """Return one joined, smooth shaded mesh object of a ribbon bow.

    Parameters
    ----------
    name : object name.
    location, rotation : object transform; geometry stays in local space with
        the knot at the origin, loops along +-X, tails towards -Z.
    width : overall span of the two loops (tip to tip), metres.
    loop_h : silhouette height of one loop, metres.  Internally the two folded
        arms are separated by ``loop_h - ribbon_w`` (clamped so they never cross).
    ribbon_w : ribbon strip width, metres.
    thickness : ribbon thickness, metres (real geometry).
    tails : number of hanging tails (1 = centred, N are spread symmetrically).
    tail_len : length of each tail along its curve, metres.
    tail_spread : total lateral spread between the outermost tails' tips, metres.
    tail_notch : depth of the shallow V notch in each tail's cut end, metres.
    loop_twist : radians the ribbon's cross section rolls towards the knot.
    droop : angle of the loop's outer tip below horizontal, radians.
    knot : build the central wrap band.
    knot_w, knot_h : knot band size, metres.
    """
    width = max(float(width), 1e-4)
    loop_h = max(float(loop_h), 1e-4)
    ribbon_w = _clamp(float(ribbon_w), 1e-5, width * 0.6)
    thickness = _clamp(float(thickness), 1e-5, ribbon_w * 0.5)
    tail_len = max(float(tail_len), 1e-5)
    tail_spread = max(float(tail_spread), 0.0)
    tail_notch = _clamp(float(tail_notch), 0.0, tail_len * 0.5)
    droop = _clamp(float(droop), -0.9, 0.9)
    n_tails = max(int(tails), 0)

    profile = _lens_profile(16)
    crown = 0.14 * ribbon_w
    sb = _Builder()

    # the two loops sit a hair apart in depth so their pinched throats (which
    # lie flat across the knot) can never intersect each other
    for sign in (-1.0, 1.0):
        _add_loop(sb, sign, width, loop_h, ribbon_w, thickness, droop,
                  float(loop_twist), profile, samples=60, crown=crown,
                  y_off=0.0012 * sign)

    if n_tails:
        if n_tails == 1:
            seats = [0.0]
        else:
            seats = [-1.0 + 2.0 * i / (n_tails - 1.0) for i in range(n_tails)]
        for i, seat in enumerate(seats):
            # just in front of the loops, still buried behind the knot's face
            y0 = -0.0030 - 0.0016 * (i % 2)
            _add_tail(sb, seat, y0, tail_len, tail_spread, ribbon_w, thickness,
                      tail_notch, profile, samples=34, crown=crown)

    if knot:
        kw = _clamp(float(knot_w), 0.002, width * 0.5)
        kh = _clamp(float(knot_h), 0.002, max(loop_h * 1.2, 0.004))
        depth = max(ribbon_w * 0.36, 0.0045)
        _add_knot(sb, kw, kh, ribbon_w, y_front=-depth, y_back=depth * 0.22)

    return _to_object(sb, name, location, rotation)
