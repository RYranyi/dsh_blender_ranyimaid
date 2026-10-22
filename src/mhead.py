"""mhead.py - head, face features (eyes/brows/mouth), ears, neck."""
import bpy
import math
from math import sin, cos, pi, sqrt, exp, atan2
from mathutils import Vector, Matrix
import mcore as C
import mprop as P
import mmat as M

TAU = 2 * pi

# ------------------------------------------------------------------ profile
# (z, rx, ry, yc, qfront)  -- chin .. crown
_PROF = [
    (0.6000, 0.0000, 0.0000, -0.0300, 2.4),
    (0.6025, 0.0270, 0.0400, -0.0292, 2.8),
    (0.6070, 0.0520, 0.0670, -0.0272, 3.1),
    (0.6140, 0.0760, 0.0900, -0.0242, 3.35),
    (0.6230, 0.0985, 0.1110, -0.0200, 3.5),
    (0.6350, 0.1185, 0.1290, -0.0155, 3.6),
    (0.6490, 0.1345, 0.1435, -0.0110, 3.9),
    (0.6660, 0.1470, 0.1545, -0.0068, 4.1),
    (0.6900, 0.1585, 0.1615, -0.0025, 4.2),
    (0.7250, 0.1700, 0.1660,  0.0015, 4.2),
    (0.7550, 0.1745, 0.1675,  0.0030, 3.95),
    (0.7900, 0.1760, 0.1665,  0.0040, 3.5),
    (0.8200, 0.1725, 0.1625,  0.0050, 2.9),
    (0.8500, 0.1650, 0.1555,  0.0060, 2.7),
    (0.8780, 0.1525, 0.1435,  0.0070, 2.5),
    (0.9020, 0.1355, 0.1285,  0.0080, 2.4),
    (0.9230, 0.1145, 0.1095,  0.0090, 2.3),
    (0.9400, 0.0895, 0.0865,  0.0100, 2.2),
    (0.9530, 0.0615, 0.0605,  0.0100, 2.1),
    (0.9630, 0.0328, 0.0328,  0.0100, 2.0),
    (0.9680, 0.0000, 0.0000,  0.0100, 2.0),
]


class Spline:
    def __init__(self, xs, ys):
        self.xs = list(xs)
        self.ys = list(ys)
        n = len(xs)
        m = [0.0] * n
        for i in range(1, n - 1):
            m[i] = (ys[i + 1] - ys[i - 1]) / (xs[i + 1] - xs[i - 1])
        m[0] = (ys[1] - ys[0]) / (xs[1] - xs[0])
        m[-1] = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        self.m = m

    def __call__(self, x):
        xs, ys, m = self.xs, self.ys, self.m
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        h = xs[hi] - xs[lo]
        s = (x - xs[lo]) / h
        h00 = 2 * s ** 3 - 3 * s ** 2 + 1
        h10 = s ** 3 - 2 * s ** 2 + s
        h01 = -2 * s ** 3 + 3 * s ** 2
        h11 = s ** 3 - s ** 2
        return h00 * ys[lo] + h10 * h * m[lo] + h01 * ys[hi] + h11 * h * m[hi]


zS = [p[0] for p in _PROF]
RX = Spline(zS, [p[1] for p in _PROF])
RY = Spline(zS, [p[2] for p in _PROF])
YC = Spline(zS, [p[3] for p in _PROF])
QF = Spline(zS, [p[4] for p in _PROF])


def _q(z):
    return QF(z)


def head_ring_xy(theta, z):
    rx, ry, yc = RX(z), RY(z), YC(z)
    s, c = sin(theta), cos(theta)
    q = _q(z)
    g = (max(0.0, 1.0 - abs(s) ** q)) ** (1.0 / q)
    y = yc - ry * g * (1.0 if c >= 0 else -1.0)
    return rx * s, y


# ---- soft face volumes (analytic so decals follow exactly) ------------------
def _bump(x, z):
    ax = abs(x)
    d = 0.0
    d += 0.0105 * exp(-((ax - 0.0900) / 0.0500) ** 2 - ((z - 0.6600) / 0.0420) ** 2)  # cheeks
    d += 0.0092 * exp(-((ax - 0.0960) / 0.0760) ** 2 - ((z - 0.7280) / 0.0540) ** 2)  # eye bulge
    d += 0.0050 * exp(-((x / 0.0420) ** 2) - ((z - 0.6220) / 0.0260) ** 2)      # chin pad
    d += 0.0022 * exp(-((ax - 0.0930) / 0.0540) ** 2 - ((z - 0.7770) / 0.0165) ** 2)  # brow
    d += 0.0026 * exp(-((ax - 0.1000) / 0.0620) ** 2 - ((z - 0.6880) / 0.0170) ** 2)  # under-eye
    # centreline profile: brow -> nose -> philtrum -> lips -> chin
    cw = exp(-(x / 0.0480) ** 2)
    pr = 0.0
    pr += 0.0030 * exp(-((z - 0.7580) / 0.0300) ** 2)   # brow ridge (forward)
    pr -= 0.0040 * exp(-((z - 0.7080) / 0.0170) ** 2)   # nose bridge dip
    pr += 0.0072 * exp(-((z - 0.6865) / 0.0125) ** 2)   # nose tip
    pr -= 0.0030 * exp(-((z - 0.6640) / 0.0120) ** 2)   # philtrum
    pr += 0.0018 * exp(-((z - 0.6480) / 0.0095) ** 2)   # lips
    pr += 0.0048 * exp(-((z - 0.6180) / 0.0160) ** 2)   # chin
    d += pr * cw
    return d


def face_y(x, z):
    rx, ry, yc = RX(z), RY(z), YC(z)
    if rx <= 1e-6:
        return yc - ry
    s = min(0.9999, abs(x) / rx)
    q = _q(z)
    g = max(0.0, 1.0 - s ** q) ** (1.0 / q)
    return yc - ry * g - _bump(x, z)


def face_point(x, z, off=0.0):
    return Vector((x, face_y(x, z) - off, z))


# ------------------------------------------------------------------ head mesh
def build_head(seg=192, rows=150):
    verts = []
    faces = []
    ztop, zbot = _PROF[-1][0], _PROF[0][0]
    verts.append((0.0, YC(ztop), ztop))
    ring_start = []
    for j in range(1, rows):
        t = j / rows
        z = ztop + (zbot - ztop) * t
        ring_start.append(len(verts))
        for i in range(seg):
            th = TAU * i / seg
            x, y = head_ring_xy(th, z)
            fm = C.smoothstep(-0.02, 0.45, cos(th))
            verts.append((x, y - _bump(x, z) * fm, z))
    bot_idx = len(verts)
    verts.append((0.0, YC(zbot), zbot))
    r0 = ring_start[0]
    for i in range(seg):
        i2 = (i + 1) % seg
        faces.append((0, r0 + i2, r0 + i))
    for j in range(len(ring_start) - 1):
        a0 = ring_start[j]
        a1 = ring_start[j + 1]
        for i in range(seg):
            i2 = (i + 1) % seg
            faces.append((a0 + i, a0 + i2, a1 + i2, a1 + i))
    last = ring_start[-1]
    for i in range(seg):
        i2 = (i + 1) % seg
        faces.append((last + i, last + i2, bot_idx))
    ob = C.new_obj("Head", verts, faces, "Maid")
    C.recalc_normals(ob)
    return ob


def build_ears():
    objs = []
    for side in (1, -1):
        x = side * (RX(0.700) * 0.965)
        e = C.sphere("Ear", (x, 0.034, 0.7010), (0.0080, 0.0185, 0.0265), seg=48, rings=32)
        objs.append(e)
    return objs


def build_neck():
    prof = []
    for i in range(18):
        t = i / 17
        z = 0.540 + (0.634 - 0.540) * t
        r = 0.0385 - 0.0030 * t + 0.0042 * C.smoothstep(0.72, 1.0, t)
        prof.append((r, z))
    ob = C.revolve("Neck", prof, seg=64)
    C.deform(ob, lambda v: Vector((v.x, v.y * 0.95 - 0.004, v.z)))
    return ob


# ================================================================== eyes
A_EYE = 0.0532
B_UP = 0.0455
B_DN = 0.0390
P_UP = 2.40
P_DN = 2.05
IRIS_R = 0.0492

_EYE_CACHE = {}


def _eye_frame(side):
    if side in _EYE_CACHE:
        return _EYE_CACHE[side]
    z = P.Z_EYE
    x = side * 0.0955
    c = face_point(x, z, 0.0)
    ang = math.radians(P.EYE_TILT_DEG) * side
    eu = Vector((side * cos(ang), 0.0, sin(ang)))
    ev = Vector((-side * sin(ang), 0.0, cos(ang)))
    _EYE_CACHE[side] = (c, eu, ev)
    return c, eu, ev


def _eye3d(side, u, v, off):
    c, eu, ev = _eye_frame(side)
    p = c + eu * u + ev * v
    return Vector((p.x, face_y(p.x, p.z) - off, p.z))


def eye_rho(th, inset=0.0, A=None, Bup=None, Bdn=None, pu=None, pd=None):
    A = A_EYE if A is None else A
    Bup = B_UP if Bup is None else Bup
    Bdn = B_DN if Bdn is None else Bdn
    pu = P_UP if pu is None else pu
    pd = P_DN if pd is None else pd
    c, s = cos(th), sin(th)
    B, p = (Bup, pu) if s >= 0 else (Bdn, pd)
    A2 = max(1e-5, A - inset)
    B2 = max(1e-5, B - inset)
    lo, hi = 0.0, max(A2, B2)
    for _ in range(36):
        mid = (lo + hi) * 0.5
        f = (abs(mid * c) / A2) ** p + (abs(mid * s) / B2) ** p - 1.0
        if f > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) * 0.5


def _disc(name, side, rho_fn, rings, seg, off, mat, uvR=1.0, cuv=(0.0, 0.0)):
    verts = [tuple(_eye3d(side, cuv[0], cuv[1], off))]
    uvs = [(0.5 + cuv[0] / (2 * uvR), 0.5 + cuv[1] / (2 * uvR))]
    for j in range(1, rings + 1):
        f = j / rings
        for i in range(seg):
            th = TAU * i / seg
            r = rho_fn(th) * f
            u = cuv[0] + r * cos(th)
            v = cuv[1] + r * sin(th)
            verts.append(tuple(_eye3d(side, u, v, off)))
            uvs.append((0.5 + u / (2 * uvR), 0.5 + v / (2 * uvR)))
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
    ob = C.new_obj(name, verts, faces, "Maid")
    ob.data.uv_layers.new(name="UVMap")
    uvl = ob.data.uv_layers[0]
    for li, loop in enumerate(ob.data.loops):
        uvl.data[li].uv = uvs[loop.vertex_index]
    C.orient_faces(ob, 1, -1)
    if mat:
        C.assign(ob, mat)
    return ob


def _strip(name, side, rail_a, rail_b, off, mat, close=False):
    verts = [tuple(_eye3d(side, u, v, off)) for (u, v) in rail_a]
    verts += [tuple(_eye3d(side, u, v, off)) for (u, v) in rail_b]
    n = len(rail_a)
    faces = []
    rng = n if close else n - 1
    for i in range(rng):
        i2 = (i + 1) % n
        faces.append((i, i2, n + i2, n + i))
    ob = C.new_obj(name, verts, faces, "Maid")
    C.orient_faces(ob, 1, -1)
    if mat:
        C.assign(ob, mat)
    return ob


IU, IV = 0.0016, 0.0028

_C_DARKTOP = C.hexc("#0E3550")
_C_NAVY2 = C.hexc("#17496B")
_C_MIDBLU = C.hexc("#2E7FA9")
_C_CYAN = C.hexc("#57ABCE")
_C_LIGHT = C.hexc("#8FD0E6")
_C_PALE = C.hexc("#A5DAEC")
_C_PALE2 = C.hexc("#D2EFF8")
_C_RIM = C.hexc("#103247")


def _iris_color(nu, nv):
    """nu,nv in [-1,1] within the iris; returns linear RGBA."""
    # vertical gradient (dark at top -> pale at bottom)
    stops = [
        (-1.00, _C_PALE), (-0.86, _C_PALE), (-0.64, _C_LIGHT),
        (-0.42, _C_CYAN), (-0.20, _C_CYAN), (0.02, _C_MIDBLU),
        (0.22, _C_NAVY2), (0.40, _C_NAVY2), (0.55, _C_DARKTOP),
        (1.00, _C_DARKTOP),
    ]
    t = max(-1.0, min(1.0, nv))
    col = stops[-1][1]
    for k in range(len(stops) - 1):
        a, ca = stops[k]
        b, cb = stops[k + 1]
        if a <= t <= b:
            f = (t - a) / (b - a)
            f = f * f * (3 - 2 * f)
            col = tuple(ca[i] * (1 - f) + cb[i] * f for i in range(4))
            break
    # radial rim darkening
    r = min(1.0, (nu * nu + nv * nv) ** 0.5)
    k = C.smoothstep(0.82, 1.0, r)
    col = tuple(col[i] * (1 - k) + _C_RIM[i] * k for i in range(4))
    # soft inner glow near the centre-bottom
    g = C.smoothstep(0.55, 0.0, r) * C.smoothstep(0.35, -0.75, nv) * 0.22
    col = tuple(col[i] * (1 - g) + _C_PALE2[i] * g for i in range(4))
    return col


def _iris_disc(side, mats, rings=46, seg=192, off=0.00110):
    verts = [tuple(_eye3d(side, IU, IV, off))]
    cols = [_iris_color(0.0, 0.0)]
    for j in range(1, rings + 1):
        f = j / rings
        for i in range(seg):
            th = TAU * i / seg
            rho = min(IRIS_R, eye_rho(th, inset=0.0) * 1.004) * f
            u = IU + rho * cos(th)
            v = IV + rho * sin(th)
            verts.append(tuple(_eye3d(side, u, v, off)))
            cols.append(_iris_color(f * cos(th), f * sin(th)))
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
    ob = C.new_obj("Iris", verts, faces, "Maid")
    C.set_vcol(ob, "Col", cols)
    C.orient_faces(ob, 1, -1)
    if mats:
        C.assign(ob, mats["iris"])
    return ob


def build_eye(side, mats):
    objs = []
    # ---------------- sclera ------------------------------------------------
    objs.append(_disc("EyeWhite", side, lambda th: eye_rho(th), 12, 112,
                      0.00035, mats["sclera"]))

    # ---------------- iris (vertex-coloured) --------------------------------
    objs.append(_iris_disc(side, mats, rings=46, seg=192))


    # ---------------- bottom spokes ----------------------------------------
    for k in range(5):
        a = math.radians(-90 + (k - 2) * 16.5)
        rr = IRIS_R * 0.845
        u0 = IU + cos(a) * rr
        v0 = IV + sin(a) * rr
        du = cos(a + pi / 2) * 0.0021
        dv = sin(a + pi / 2) * 0.0021
        t = 0.0042
        ra = [(u0 - du, v0 - dv), (u0 + du, v0 + dv)]
        rb = [(u0 - du + cos(a) * t, v0 - dv + sin(a) * t),
              (u0 + du + cos(a) * t, v0 + dv + sin(a) * t)]
        objs.append(_strip("IrisTick", side, ra, rb, 0.00150, mats["irisline"]))

    # ---------------- highlights -------------------------------------------
    # light comes from upper-left of the image: same world side for both eyes
    hl_u = -side * 0.0125
    objs.append(_disc("EyeHL1", side, lambda th: 0.0140, 10, 56, 0.00175,
                      mats["highlight"], cuv=(hl_u, 0.0165), uvR=IRIS_R))
    objs.append(_disc("EyeHL2", side, lambda th: 0.0050, 8, 40, 0.00175,
                      mats["highlight"], cuv=(side * 0.0165, -0.0165), uvR=IRIS_R))

    # ---------------- upper lash -------------------------------------------
    n = 64
    rail_in, rail_out = [], []
    for i in range(n):
        t = i / (n - 1)
        u = -A_EYE * 1.015 + (A_EYE * 2.075) * t
        sc = min(1.0, abs(u) / A_EYE)
        v = B_UP * (1 - sc ** P_UP) ** (1 / P_UP)
        thk = 0.0022 + 0.0098 * C.smoothstep(0.0, 0.40, t) * (1.0 - 0.40 * C.smoothstep(0.86, 1.0, t))
        flick = C.smoothstep(0.70, 1.0, t)
        # outer flick sweeps up and out
        du = flick * 0.0060
        dv = flick * 0.0075
        rail_in.append((u, v - 0.0008))
        rail_out.append((u + du * 0.35, v + thk + dv * 0.25))
    objs.append(_strip("Lash", side, rail_in, rail_out, 0.00190, mats["lash"]))

    # ---------------- lower lid line ---------------------------------------
    n2 = 44
    ra, rb = [], []
    for i in range(n2):
        t = i / (n2 - 1)
        u = -A_EYE * 0.955 + (A_EYE * 1.91) * t
        sc = min(0.999, abs(u) / A_EYE)
        v = -B_DN * (1 - sc ** P_DN) ** (1 / P_DN)
        ra.append((u, v + 0.0013))
        rb.append((u, v - 0.0027))
    objs.append(_strip("LowerLid", side, ra, rb, 0.00125, mats["irisline"]))

    # ---------------- red accents ------------------------------------------
    # (a) eyelid crease slash just above the lash, outer third
    ra, rb = [], []
    for i in range(16):
        t = i / 15
        u0 = A_EYE * 0.34 + A_EYE * 0.46 * t
        sc = min(0.999, abs(u0) / A_EYE)
        v0 = B_UP * (1 - sc ** P_UP) ** (1 / P_UP) + 0.0128 + 0.0016 * t
        w = 0.00135 * (1 - 0.62 * abs(2 * t - 1) ** 2)
        ra.append((u0, v0 - w))
        rb.append((u0, v0 + w))
    objs.append(_strip("RedAccentA", side, ra, rb, 0.00130, mats["red"]))
    # (b) outer corner slash, inside the eye
    ra, rb = [], []
    for i in range(16):
        t = i / 15
        u0 = A_EYE * 0.945
        v0 = 0.0125 - 0.0265 * t
        w = 0.0022 * (1 - 0.45 * abs(2 * t - 1) ** 2)
        ra.append((u0 - w, v0))
        rb.append((u0 + w, v0))
    objs.append(_strip("RedAccentB", side, ra, rb, 0.00132, mats["red"]))
    return objs


def build_eyebrow(side):
    pts = []
    widths = []
    n = 30
    for i in range(n):
        t = i / (n - 1)
        x = (0.0500 + 0.0850 * t)
        z = 0.7895 + 0.0050 * sin(pi * min(1.0, t * 1.03) ** 0.9) - 0.0030 * t
        thk = 0.0030 * (1 - 0.78 * abs(2 * t - 1) ** 2.4) + 0.0005
        pts.append((side * x, 0.0, z))
        widths.append(thk)
    verts = []
    for i, p in enumerate(pts):
        x, _, z = p
        off = 0.0020
        if i == 0:
            dx, dz = pts[1][0] - x, pts[1][2] - z
        elif i == n - 1:
            dx, dz = x - pts[-2][0], z - pts[-2][2]
        else:
            dx = pts[i + 1][0] - pts[i - 1][0]
            dz = pts[i + 1][2] - pts[i - 1][2]
        L = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / L, dx / L
        w = widths[i]
        verts.append((x - nx * w, face_y(x - nx * w, z - nz * w) - off, z - nz * w))
        verts.append((x + nx * w, face_y(x + nx * w, z + nz * w) - off, z + nz * w))
    faces = []
    for i in range(n - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    ob = C.new_obj("Brow", verts, faces, "Maid")
    C.orient_faces(ob, 1, -1)
    return ob


def build_mouth():
    w = 0.0245
    n = 53
    pts = []
    for i in range(n):
        t = i / (n - 1)
        u = -w + 2 * w * t
        k = u / w
        z = P.Z_MOUTH - 0.0030 * (1 - k * k) + 0.0015 * exp(-(u / 0.0050) ** 2)
        pts.append((u, z))
    rail_a, rail_b = [], []
    r = 0.00132
    for (u, z) in pts:
        y = face_y(u, z) - 0.0005
        rail_a.append((u, y - r * 0.5, z + r))
        rail_b.append((u, y - r * 0.5, z - r))
    verts = [tuple(v) for v in rail_a] + [tuple(v) for v in rail_b]
    faces = []
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))
    ob = C.new_obj("Mouth", verts, faces, "Maid")
    C.orient_faces(ob, 1, -1)
    C.add_solidify(ob, 0.0011, offset=0.0)
    C.shade_smooth(ob)
    return ob


def _noshab(ob):
    try:
        ob.visible_shadow = False
    except Exception:
        pass
    return ob


def build_face(mats):
    objs = []
    for side in (1, -1):
        objs += [_noshab(o) for o in build_eye(side, mats)]
        b = _noshab(build_eyebrow(side))
        C.assign(b, mats["brow"])
        objs.append(b)
    mo = _noshab(build_mouth())
    C.assign(mo, mats["mouth"])
    objs.append(mo)
    return objs


def build_head_group(mats, seg=192, rows=150):
    head = build_head(seg, rows)
    C.assign(head, mats["skin"])
    parts = [head]
    for e in build_ears():
        C.assign(e, mats["skin"])
        parts.append(e)
    neck = build_neck()
    C.assign(neck, mats["skin"])
    parts.append(neck)
    parts += build_face(mats)
    return parts
