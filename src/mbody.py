"""mbody.py - body under the clothes: torso, arms, legs, simple hands."""
import bpy
import math
from math import sin, cos, pi, sqrt, exp
from mathutils import Vector, Matrix
import mcore as C
import mprop as P
import mhead as HD

TAU = 2 * pi

TORSO = [
    # (z, rx, ry, yc)
    (0.3300, 0.0920, 0.0770, 0.0000),
    (0.3600, 0.0930, 0.0785, 0.0000),
    (0.3900, 0.0930, 0.0785, 0.0000),
    (0.4200, 0.0895, 0.0760, -0.0010),
    (0.4480, 0.0845, 0.0720, -0.0015),
    (0.4750, 0.0865, 0.0730, -0.0015),
    (0.5000, 0.0895, 0.0750, -0.0010),
    (0.5250, 0.0910, 0.0755, -0.0005),
    (0.5450, 0.0900, 0.0740, 0.0000),
    (0.5600, 0.0840, 0.0700, 0.0000),
    (0.5720, 0.0700, 0.0620, 0.0000),
    (0.5820, 0.0540, 0.0500, -0.0010),
    (0.5920, 0.0410, 0.0400, -0.0020),
    (0.6000, 0.0370, 0.0370, -0.0030),
    (0.6080, 0.0362, 0.0362, -0.0035),
]
ZS = [p[0] for p in TORSO]
TRX = HD.Spline(ZS, [p[1] for p in TORSO])
TRY = HD.Spline(ZS, [p[2] for p in TORSO])
TYC = HD.Spline(ZS, [p[3] for p in TORSO])


def torso_point(u, z, q=2.5, off=0.0):
    rx, ry, yc = TRX(z) + off, TRY(z) + off, TYC(z)
    s, c = sin(u), cos(u)
    g = max(0.0, 1.0 - abs(s) ** q) ** (1.0 / q)
    return Vector((rx * s, yc - ry * g * (1.0 if c >= 0 else -1.0), z))


def build_torso(seg=96, rows=70):
    z0, z1 = ZS[0], ZS[-1]
    verts = []
    faces = []
    for j in range(rows + 1):
        z = z0 + (z1 - z0) * j / rows
        for i in range(seg):
            u = TAU * i / seg
            p = torso_point(u, z)
            verts.append(tuple(p))
    for j in range(rows):
        for i in range(seg):
            i2 = (i + 1) % seg
            a = j * seg + i
            b = j * seg + i2
            c = (j + 1) * seg + i2
            d = (j + 1) * seg + i
            faces.append((a, b, c, d))
    faces.append(tuple(range(seg - 1, -1, -1)))
    base = rows * seg
    faces.append(tuple(base + i for i in range(seg)))
    ob = C.new_obj("Torso", verts, faces, "Maid")
    C.recalc_normals(ob)
    C.shade_smooth(ob)
    return ob


# ------------------------------------------------------------------ limbs
def _limb(name, path_fn, r_fn, seg=40, rings=48, cap=True):
    pts = [path_fn(i / (rings - 1)) for i in range(rings)]
    rs = [r_fn(i / (rings - 1)) for i in range(rings)]
    ob = C.tube(name, pts, rs, seg=seg, caps=cap)
    C.shade_smooth(ob)
    return ob



def _smooth_rad(t, pts):
    """Catmull-Rom through (t, r) control points -> C1 radius profile."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    i = 0
    while i < len(xs) - 2 and t > xs[i + 1]:
        i += 1
    # neighbours for tangents
    i0 = max(0, i - 1)
    i3 = min(len(xs) - 1, i + 2)
    x0, x1, x2, x3 = xs[i0], xs[i], xs[i + 1], xs[i3]
    y0, y1, y2, y3 = ys[i0], ys[i], ys[i + 1], ys[i3]
    dx = x2 - x1
    m1 = (y2 - y0) / max(1e-6, x2 - x0)
    m2 = (y3 - y1) / max(1e-6, x3 - x1)
    h = (t - x1) / max(1e-6, dx)
    h2 = h * h
    h3 = h2 * h
    return ((2 * h3 - 3 * h2 + 1) * y1 + (h3 - 2 * h2 + h) * dx * m1 +
            (-2 * h3 + 3 * h2) * y2 + (h3 - h2) * dx * m2)


def build_leg(side):
    def path(t):
        z = 0.400 - (0.400 - 0.048) * t
        x = side * (0.0475 - 0.0035 * C.smoothstep(0.55, 1.0, t))
        y = -0.004 + 0.010 * C.smoothstep(0.6, 1.0, t)
        return Vector((x, y, z))

    def rad(t):
        return _smooth_rad(t, [(0.00, 0.0430), (0.18, 0.0400), (0.38, 0.0330),
                               (0.55, 0.0290), (0.70, 0.0305), (0.85, 0.0235),
                               (0.95, 0.0180), (1.00, 0.0175)])

    return _limb("Leg", path, rad, seg=40, rings=54)


def build_arm(side):
    ctrl = [Vector((side * 0.0870, -0.0030, 0.5580)),
            Vector((side * 0.0975, -0.0100, 0.5060)),
            Vector((side * 0.1080, -0.0200, 0.4650)),
            Vector((side * 0.1190, -0.0450, 0.4250)),
            Vector((side * 0.1275, -0.0790, 0.3900)),
            Vector((side * 0.1330, -0.1050, 0.3570))]
    spine = C.polyline_resample(ctrl, 80)

    def path(t):
        i = min(len(spine) - 1, max(0, int(round(t * (len(spine) - 1)))))
        return spine[i]

    RAD = [(0.00, 0.0300), (0.08, 0.0338), (0.20, 0.0324), (0.34, 0.0292),
           (0.48, 0.0264), (0.62, 0.0246), (0.76, 0.0228), (0.90, 0.0204),
           (1.00, 0.0188)]

    def rad(t):
        return _smooth_rad(t, RAD)

    return _limb("Arm", path, rad, seg=48, rings=80)


def _hand_local(side):
    """Build a hand in local space: wrist at origin, fingers +Z, palm -Y, thumb +X (R)."""
    mir = -1.0 if side < 0 else 1.0
    objs = []
    # ---- palm: superellipse loft ----
    ring_def = [
        (-0.0060, 0.0184, 0.0126),
        (0.0000, 0.0198, 0.0134),
        (0.0080, 0.0236, 0.0150),
        (0.0160, 0.0262, 0.0158),
        (0.0240, 0.0268, 0.0156),
        (0.0310, 0.0258, 0.0148),
        (0.0365, 0.0236, 0.0134),
        (0.0400, 0.0208, 0.0116),
    ]
    seg = 48
    q = 2.7
    rings = []
    for (z, rx, ry) in ring_def:
        ring = []
        for i in range(seg):
            a = TAU * i / seg
            sx, cy = sin(a), cos(a)
            g = max(0.0, 1.0 - min(1.0, abs(sx)) ** q) ** (1.0 / q)
            ring.append(Vector((rx * sx, -ry * g * (1.0 if cy >= 0 else -1.0), z)))
        rings.append(ring)
    verts = [tuple(Vector((p.x * mir, p.y, p.z))) for r in rings for p in r]
    faces = []
    for j in range(len(rings) - 1):
        for i in range(seg):
            i2 = (i + 1) % seg
            a0 = j * seg + i
            b0 = j * seg + i2
            faces.append((a0, b0, b0 + seg, a0 + seg))
    faces.append(tuple(range(seg - 1, -1, -1)))
    base = (len(rings) - 1) * seg
    faces.append(tuple(base + i for i in range(seg)))
    palm = C.new_obj("Palm", verts, faces, "Maid")
    C.recalc_normals(palm)
    objs.append(palm)

    # ---- fingers ----
    fspec = [
        # (x, base_z, length, r0, r1, spread)
        (0.0186, 0.0340, 0.0298, 0.0092, 0.0080, 0.30),
        (0.0062, 0.0360, 0.0332, 0.0096, 0.0084, 0.10),
        (-0.0070, 0.0345, 0.0312, 0.0092, 0.0080, -0.12),
        (-0.0190, 0.0308, 0.0252, 0.0082, 0.0071, -0.34),
    ]
    for k, (fx, bz, ln, r0, r1, sp) in enumerate(fspec):
        pts = []
        n = 14
        for i in range(n):
            t = i / (n - 1)
            x = fx * (1.0 + sp * t * 0.9)
            y = -0.0040 - 0.0155 * (t ** 1.8)
            z = bz + ln * t
            pts.append(Vector((x * mir, y, z)))
        radii = [r0 * (1 - t) + r1 * t for t in [i / (n - 1) for i in range(n)]]
        fg = C.tube("Finger%d" % k, pts, radii, seg=22, caps=True)
        # rounded tip
        tip = C.sphere("FingerTip%d" % k, (pts[-1].x, pts[-1].y, pts[-1].z),
                       (r1, r1, r1 * 0.95), seg=20, rings=14)
        objs.append(fg)
        objs.append(tip)

    # ---- thumb ----
    tp = [Vector((0.0180 * mir, -0.0060, 0.0120)),
          Vector((0.0245 * mir, -0.0110, 0.0220)),
          Vector((0.0270 * mir, -0.0150, 0.0320)),
          Vector((0.0255 * mir, -0.0165, 0.0395))]
    tr = [0.0102, 0.0096, 0.0088, 0.0080]
    thumb = C.tube("Thumb", tp, tr, seg=22, caps=True)
    tip = C.sphere("ThumbTip", (tp[-1].x, tp[-1].y, tp[-1].z), (0.0080, 0.0080, 0.0076),
                   seg=20, rings=14)
    objs.append(thumb)
    objs.append(tip)
    for o in objs:
        C.shade_smooth(o)
    h = C.join_objs(objs, "Hand")
    C.recalc_normals(h)
    C.shade_smooth(h)
    return h


_FOREARM_DIR = Vector((0.0125, -0.0405, -0.0470))   # p2 -> p3 of the arm spine


def build_hand(side, wrist):
    """Place a hand at the wrist, fingers along the forearm's true end tangent."""
    h = _hand_local(side)
    F = Vector((side * _FOREARM_DIR.x, _FOREARM_DIR.y, _FOREARM_DIR.z)).normalized()
    P = Vector((side * -1.0, 0.14, 0.0)).normalized()
    e3 = F
    e2 = -P
    e1 = e2.cross(e3).normalized()
    M = Matrix(((e1.x, e2.x, e3.x), (e1.y, e2.y, e3.y), (e1.z, e2.z, e3.z)))
    for v in h.data.vertices:
        v.co = Vector(wrist) + M @ v.co
    h.data.update()
    return h


# ------------------------------------------------------------------ feet
_FOOT_TAB = [
    # (y, half_width, z_bottom, z_top)
    (0.0465, 0.0150, 0.0270, 0.0400),
    (0.0400, 0.0225, 0.0132, 0.0470),
    (0.0300, 0.0270, 0.0120, 0.0495),
    (0.0140, 0.0300, 0.0116, 0.0500),
    (0.0000, 0.0308, 0.0114, 0.0475),
    (-0.0160, 0.0310, 0.0114, 0.0420),
    (-0.0320, 0.0308, 0.0114, 0.0360),
    (-0.0480, 0.0300, 0.0114, 0.0305),
    (-0.0580, 0.0288, 0.0116, 0.0290),
    (-0.0660, 0.0268, 0.0118, 0.0262),
]

# (dx from foot centre, radius, length, z centre)   -- inner (big toe) first
_TOES = [
    (-0.0172, 0.0096, 0.0225, 0.0205),
    (-0.0046, 0.0074, 0.0212, 0.0195),
    (0.0052, 0.0069, 0.0192, 0.0190),
    (0.0142, 0.0063, 0.0162, 0.0185),
    (0.0222, 0.0055, 0.0122, 0.0180),
]


def _ring_xz(fx, y, w, zb, zt, seg, pad=0.0):
    zc = 0.5 * (zb + zt)
    rz = 0.5 * (zt - zb) + pad
    rz = max(rz, 0.0012)
    out = []
    for i in range(seg):
        th = TAU * i / seg
        c, sn = cos(th), sin(th)
        e = 2.6 if sn < 0 else 2.0
        g = (abs(c) ** e + abs(sn) ** e) ** (-1.0 / e)
        out.append(Vector((fx + (w + pad) * c * g,
                           y,
                           max(0.004, zc) + rz * sn * g + (pad * 0.35 if sn < 0 else 0.0))))
    return out


def _capsule(pts, radii, seg=18, squash=0.86):
    """Tapered capsule along a polyline; returns (verts, faces)."""
    rings = []
    for i, p in enumerate(pts):
        r = radii[i]
        t = pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]
        t.normalize()
        up = Vector((0, 0, 1))
        side = t.cross(up)
        if side.length < 1e-5:
            side = Vector((1, 0, 0))
        side.normalize()
        up2 = side.cross(t).normalized()
        ring = []
        for k in range(seg):
            a = TAU * k / seg
            ring.append(p + side * (r * cos(a)) + up2 * (r * squash * sin(a)))
        rings.append(ring)
    verts = [tuple(p) for r in rings for p in r]
    faces = []
    n = seg
    for j in range(len(rings) - 1):
        for i in range(n):
            i2 = (i + 1) % n
            a = j * n + i
            b = j * n + i2
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(range(n - 1, -1, -1)))
    base = (len(rings) - 1) * n
    faces.append(tuple(base + i for i in range(n)))
    return verts, faces


def _foot_geo(side, pad=0.0, seg=44):
    """Foot last (heel->metatarsal) + ankle column + five toes, optionally padded."""
    fx = side * 0.0468
    ay = 0.006
    verts, faces = [], []
    rings = []
    for (y, w, zb, zt) in _FOOT_TAB:
        rings.append(_ring_xz(fx, y + (pad * 0.8 if y > 0 else -pad * 0.4),
                              w, zb, zt, seg, pad))
    verts += [tuple(p) for r in rings for p in r]
    n = seg
    for j in range(len(rings) - 1):
        for i in range(n):
            i2 = (i + 1) % n
            a = j * n + i
            b = j * n + i2
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(range(n - 1, -1, -1)))
    base = (len(rings) - 1) * n
    faces.append(tuple(base + i for i in range(n)))

    # ---- toes ----
    for (dx, r, ln, zc) in _TOES:
        x = fx + dx                   # dx is already inner->outer for this foot
        y0 = -0.0560 - pad * 0.2
        pts, rad = [], []
        m = 6
        for i in range(m + 1):
            t = i / m
            pts.append(Vector((x + dx * 0.06 * t,
                               y0 - (ln - pad * 0.6) * t,
                               zc - 0.0035 * t * t)))
            rad.append(r * (1.0 - 0.28 * t) + pad * 0.9)
        vv, ff = _capsule(pts, rad, seg=16, squash=0.84)
        off = len(verts)
        verts += vv
        faces += [tuple(i + off for i in f) for f in ff]

    # ---- ankle column (hidden inside the sock / shoe) ----
    ank = []
    for i in range(16):
        t = i / 15
        z = 0.0390 + (0.0840 - 0.0390) * t
        r = 0.0238 - 0.0030 * (t ** 1.3) + pad
        ank.append((fx - side * 0.0004 * t, ay + 0.001 * t, z, r))
    rings2 = []
    for (x, y, z, r) in ank:
        ring = []
        for i in range(seg):
            th = TAU * i / seg
            ring.append(Vector((x + r * 1.03 * cos(th), y + r * 0.95 * sin(th), z)))
        rings2.append(ring)
    o2 = len(verts)
    for r in rings2:
        verts += [tuple(p) for p in r]
    for j in range(len(rings2) - 1):
        for i in range(n):
            i2 = (i + 1) % n
            a = o2 + j * n + i
            b = o2 + j * n + i2
            faces.append((a, b, b + n, a + n))
    faces.append(tuple(o2 + i for i in range(n - 1, -1, -1)))
    bb = o2 + (len(rings2) - 1) * n
    faces.append(tuple(bb + i for i in range(n)))
    return verts, faces


def build_foot(side, pad=0.0, name="Foot"):
    v, f = _foot_geo(side, pad)
    ob = C.new_obj(name, v, f, "Maid")
    C.recalc_normals(ob)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_body(mats):
    objs = [build_torso()]
    for s in (1, -1):
        objs.append(build_leg(s))
        objs.append(build_arm(s))
        wr = Vector((s * 0.1455, -0.1215, 0.3570))
        # client-tuned hand placement per side
        wr += Vector((-0.00700, 0.01294, -0.00468)) if s < 0 else \
            Vector((0.01085, 0.01406, -0.00454))
        objs.append(build_hand(s, wr))
        foot = build_foot(s, 0.0, "Foot")
        foot.scale = (1.0, 0.971, 1.0)
        C.assign(foot, mats["skin"])
        sock_foot = build_foot(s, 0.0020, "SockFoot")
        sock_foot.scale = (1.0, 0.971, 1.0)
        C.assign(sock_foot, mats["sock"])
        objs.append(foot)
        objs.append(sock_foot)
    for o in objs:
        if not o.data.materials:
            C.assign(o, mats["skin"])
    return objs
