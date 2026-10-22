"""mhair.py - bob haircut: cap with pointed tips, layered fringe, side locks."""
import bpy
import math
from math import sin, cos, pi, sqrt, exp
from mathutils import Vector
import mcore as C
import mprop as P
import mhead as HD

TAU = 2 * pi
Z_TOP = 0.968          # skull crown
Z_HAIR_TOP = 0.9855
Z_RIM_FRONT = 0.8270   # hairline at the forehead (hidden under fringe)
Z_RIM_SIDE = 0.6480
Z_RIM_BACK = 0.6070

# hair thickness (offset along the skull normal)
_T = [
    (0.6000, 0.0750),
    (0.6150, 0.0800),
    (0.6400, 0.0790),
    (0.6700, 0.0740),
    (0.7000, 0.0660),
    (0.7300, 0.0610),
    (0.7600, 0.0570),
    (0.8000, 0.0520),
    (0.8500, 0.0450),
    (0.9000, 0.0360),
    (0.9400, 0.0260),
    (0.9680, 0.0180),
]
T_SPLINE = HD.Spline([p[0] for p in _T], [p[1] for p in _T])


def t_of_z(z):
    return T_SPLINE(z)


def skull_point(u, z):
    x, y = HD.head_ring_xy(u, z)
    return Vector((x, y, z))


def skull_normal(u, z, eps=2e-3):
    du = 4e-3
    a = skull_point(u + du, z) - skull_point(u - du, z)
    b = skull_point(u, min(0.9675, z + eps)) - skull_point(u, max(0.6005, z - eps))
    n = b.cross(a)
    if n.length < 1e-9:
        return Vector((0, 0, 1))
    n.normalize()
    if n.dot(skull_point(u, z) - Vector((0.0, 0.004, 0.79))) < 0:
        n = -n
    return n


def hair_point(u, z, extra=0.0):
    return skull_point(u, z) + skull_normal(u, z) * (t_of_z(z) + extra)


def hair_normal(u, z):
    return skull_normal(u, z)


# ------------------------------------------------------------------ rim curve
def rim_z(u):
    """Hair rim height as a function of angle u (0 = front)."""
    a = abs(((u + pi) % TAU) - pi)          # 0..pi, distance from front

    def lerp3(x, xs, ys):
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                f = (x - xs[i]) / (xs[i + 1] - xs[i])
                f = f * f * (3 - 2 * f)
                return ys[i] * (1 - f) + ys[i + 1] * f
        return ys[-1]

    base = lerp3(a, [0.0, 0.45, 0.95, 1.55, 2.10, 2.55, pi],
                 [0.8300, 0.8150, 0.7620, 0.6950, 0.6520, 0.6200, 0.6050])
    # pointed tips
    k = 14.0
    tt = (0.5 + 0.5 * cos(k * u + 0.30)) ** 1.20
    fade = C.smoothstep(0.30, 0.80, a) * (1.0 - C.smoothstep(2.80, 3.10, a) * 0.30)
    return base - 0.0125 * tt * fade


def build_cap(seg=256, rows=76):
    """Main hair volume: skull surface offset by t(z), open at the face."""
    verts = []
    faces = []
    # pole
    verts.append(tuple(Vector((0.0, 0.004, 0.0)) + Vector((0, 0, Z_HAIR_TOP))))
    ring_start = []
    for j in range(1, rows + 1):
        v = j / rows
        ev = v ** 1.06
        ring_start.append(len(verts))
        for i in range(seg):
            u = TAU * i / seg
            zr = rim_z(u)
            z = Z_TOP + (zr - Z_TOP) * ev
            rip = 0.0
            p = hair_point(u, z, rip)
            verts.append((p.x, p.y, p.z))
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
    ob = C.new_obj("HairCap", verts, faces, "Maid")
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0080, offset=-1.0, even=False, rim=True)
    C.shade_smooth(ob)
    return ob


# ------------------------------------------------------------------ strands
def _cr(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return (0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))


def strand_spine(ctrl, n=26, extra=0.0):
    """ctrl: list of (u_deg, z). Returns (points, normals, tangents)."""
    UZ = [(math.radians(u), z) for (u, z) in ctrl]
    ext = [UZ[0]] + UZ + [UZ[-1]]
    pts = []
    for i in range(len(ext) - 3):
        for s in range(10):
            t = s / 10
            u = _cr(ext[i][0], ext[i + 1][0], ext[i + 2][0], ext[i + 3][0], t)
            z = _cr(ext[i][1], ext[i + 1][1], ext[i + 2][1], ext[i + 3][1], t)
            pts.append((u, z))
    pts.append(UZ[-1])
    # resample uniformly
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + math.hypot((pts[i][0] - pts[i - 1][0]) * 0.18,
                                    pts[i][1] - pts[i - 1][1]))
    total = L[-1]
    out = []
    for k in range(n):
        s = total * k / (n - 1)
        i = 0
        while i < len(L) - 2 and L[i + 1] < s:
            i += 1
        seg = max(1e-9, L[i + 1] - L[i])
        f = (s - L[i]) / seg
        out.append((pts[i][0] * (1 - f) + pts[i + 1][0] * f,
                    pts[i][1] * (1 - f) + pts[i + 1][1] * f))
    P3 = [hair_point(u, z, extra) for (u, z) in out]
    N3 = [hair_normal(u, z) for (u, z) in out]
    return P3, N3


def build_strand(name, ctrl, wmax, thmax, n=30, seg=14, extra=0.0,
                 w_pow=0.55, taper_start=0.10, tip_extra=0.0, lift=0.0):
    P3, N3 = strand_spine(ctrl, n, extra)
    tang = []
    for i in range(n):
        if i == 0:
            t = P3[1] - P3[0]
        elif i == n - 1:
            t = P3[-1] - P3[-2]
        else:
            t = P3[i + 1] - P3[i - 1]
        tang.append(t.normalized())
    verts = []
    rings = []
    for i in range(n):
        tt = i / (n - 1)
        w = wmax * (sin(pi * min(1.0, (taper_start + 0.90 * tt))) ** w_pow)
        w *= (1.0 - tt) ** 0.62
        th = thmax * (1.0 - tt) ** 0.42
        nv = N3[i]
        side = tang[i].cross(nv).normalized()
        center = P3[i] + nv * (lift + th * 0.10)
        ring = []
        if w <= 1e-7 and th <= 1e-7:
            ring = [center + nv * (tip_extra * 0.0)] * seg
        else:
            for k in range(seg):
                a = TAU * k / seg
                ring.append(center + side * (w * cos(a)) + nv * (th * sin(a) + th * 0.35))
        rings.append(ring)
    # build rings into mesh (collapse duplicate tip ring)
    vidx = []
    for ring in rings:
        base = len(verts)
        for p in ring:
            verts.append(tuple(p))
        vidx.append(base)
    faces = []
    for i in range(n - 1):
        a0 = vidx[i]
        a1 = vidx[i + 1]
        for k in range(seg):
            k2 = (k + 1) % seg
            faces.append((a0 + k, a0 + k2, a1 + k2, a1 + k))
    faces.append(tuple(vidx[0] + k for k in range(seg - 1, -1, -1)))
    faces.append(tuple(vidx[-1] + k for k in range(seg)))
    ob = C.new_obj(name, verts, faces, "Maid")
    C.recalc_normals(ob)
    C.shade_smooth(ob)
    return ob



def build_fringe_mass(nu=170, nv=48):
    """One continuous fringe block hugging the forehead, with a few soft points."""
    def ptf(uu, vv):
        t = uu
        u = math.radians(-104.0 + 208.0 * t)
        # tip line: 4 broad clumps + a gentle lift at the temples
        c = 0.5 + 0.5 * math.cos(TAU * 4.0 * t + 0.55)
        ztip = 0.8040 - 0.0340 * (c ** 1.25)
        edge = max(0.0, abs(t - 0.5) * 2.0 - 0.74) / 0.26
        ztip += 0.0450 * (edge ** 1.7)
        zroot = 0.9650
        z = zroot + (ztip - zroot) * (vv ** 0.92)
        off = 0.0055 + 0.0105 * (vv ** 0.80)
        off += 0.0022 * math.sin(TAU * 5.0 * t + 0.3) * vv
        q = hair_point(u, max(0.70, z), off)
        return (q.x, q.y, q.z)

    ob = C.grid("FringeMass", ptf, nu, nv, close_u=False)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0060, offset=0.0, even=True, rim=True)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_fringe():
    """Layered bangs sweeping over the forehead."""
    specs = [
        # name, ctrl [(u_deg,z)...], width, thickness, extra
        ("Fringe_0", [(-84, 0.918), (-88, 0.832), (-83, 0.748), (-78, 0.694)], 0.033, 0.0115, 0.0010),
        ("Fringe_1", [(-58, 0.946), (-64, 0.862), (-59, 0.784), (-52, 0.738)], 0.038, 0.0125, 0.0022),
        ("Fringe_2", [(-34, 0.958), (-41, 0.872), (-35, 0.792), (-28, 0.752)], 0.037, 0.0120, 0.0034),
        ("Fringe_3", [(-9, 0.964), (-13, 0.876), (-8, 0.798), (-2, 0.770)], 0.035, 0.0115, 0.0028),
        ("Fringe_4", [(16, 0.962), (10, 0.876), (14, 0.796), (20, 0.762)], 0.037, 0.0120, 0.0024),
        ("Fringe_5", [(40, 0.954), (34, 0.870), (40, 0.790), (48, 0.746)], 0.039, 0.0125, 0.0030),
        ("Fringe_6", [(62, 0.942), (57, 0.860), (62, 0.780), (69, 0.730)], 0.034, 0.0115, 0.0012),
        ("Fringe_1b", [(-48, 0.952), (-54, 0.866), (-49, 0.784), (-43, 0.740)], 0.030, 0.0105, 0.0046),
        ("Fringe_2b", [(-22, 0.962), (-28, 0.874), (-22, 0.792), (-16, 0.760)], 0.029, 0.0100, 0.0050),
        ("Fringe_3b", [(2, 0.966), (-2, 0.878), (2, 0.798), (8, 0.772)], 0.028, 0.0098, 0.0044),
        ("Fringe_4b", [(28, 0.960), (22, 0.872), (27, 0.790), (34, 0.756)], 0.030, 0.0102, 0.0048),
        ("Fringe_5b", [(52, 0.950), (46, 0.866), (52, 0.784), (59, 0.738)], 0.029, 0.0100, 0.0042),
        # thin accent locks on top for the layered look
        ("FringeTop_0", [(-24, 0.958), (-50, 0.926), (-66, 0.876), (-64, 0.818)], 0.038, 0.0080, 0.0062),
        ("FringeTop_1", [(8, 0.962), (-12, 0.940), (-28, 0.900), (-24, 0.846)], 0.042, 0.0085, -0.0040),
        ("FringeTop_2", [(45, 0.952), (32, 0.924), (29, 0.880), (35, 0.834)], 0.036, 0.0075, -0.0032),
    ]
    objs = [build_fringe_mass()]
    return objs
    objs = []
    for name, ctrl, w, th, extra in specs:
        ctrl = list(ctrl)
        if not name.startswith("FringeTop"):
            ctrl[-1] = (ctrl[-1][0], ctrl[-1][1] + 0.0320)
            z2 = ctrl[-2][1] + 0.0120
            ctrl[-2] = (ctrl[-2][0], z2)
        objs.append(build_strand(name, ctrl, w, th, n=36, seg=16, extra=extra))
    return objs


def build_locks():
    """Side locks in front of the ears + nape strands."""
    specs = [
        ("Lock_0", [(-76, 0.880), (-84, 0.792), (-82, 0.702), (-76, 0.640)], 0.034, 0.0150, 0.0020),
        ("Lock_1", [(-98, 0.866), (-106, 0.782), (-104, 0.700), (-98, 0.656)], 0.030, 0.0140, 0.0005),
    ]
    objs = []
    for name, ctrl, w, th, extra in specs:
        objs.append(build_strand(name, ctrl, w, th, n=32, seg=16, extra=extra))
        if name.startswith("Lock"):
            objs.append(build_strand(name + "_mir", [(-u, z) for (u, z) in ctrl],
                                     w, th, n=32, seg=16, extra=extra))
    return objs


def build_hair(mats):
    cap = build_cap()
    C.assign(cap, mats["hair"])
    objs = [cap]
    for o in build_fringe() + build_locks():
        C.assign(o, mats["hair"])
        objs.append(o)
    return objs
