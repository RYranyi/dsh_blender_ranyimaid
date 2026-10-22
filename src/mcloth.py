"""mcloth.py - maid outfit: dress, apron, collar, sleeves, ruffles, bow,
headband, panties, socks, shoes."""
import bpy
import math
import sys
import os
from math import sin, cos, pi, sqrt, exp, radians, asin
from mathutils import Vector, Matrix
import mcore as C
import mprop as P
import mhead as HD
import mbody as BD

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else r"E:\dsh\maid_chibi\src"
for _p in (os.path.join(_HERE, "lib"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import ruffle as RF
import bow as BW
import shoe as SH
import hand as HD2

TAU = 2 * pi


def _prof(pts):
    xs = [p[0] for p in pts]
    return HD.Spline(xs, [p[1] for p in pts])


def _lerp_tab(t, tab):
    """tab: [(x,y)]; linear interp with smoothstep."""
    if t <= tab[0][0]:
        return tab[0][1]
    for i in range(len(tab) - 1):
        if tab[i][0] <= t <= tab[i + 1][0]:
            f = (t - tab[i][0]) / (tab[i + 1][0] - tab[i][0])
            f = f * f * (3 - 2 * f)
            return tab[i][1] * (1 - f) + tab[i + 1][1] * f
    return tab[-1][1]


def _shade(ob, rough=None, mat=None):
    C.shade_smooth(ob)
    return ob


# ================================================================== dress
SKIRT_RX = [(0.2040, 0.1830), (0.2230, 0.1905), (0.2440, 0.1930), (0.2900, 0.1880),
            (0.3350, 0.1630), (0.3780, 0.1390), (0.4200, 0.1150), (0.4550, 0.0930)]
SKIRT_RY = [(0.2040, 0.1360), (0.2230, 0.1400), (0.2440, 0.1402), (0.2900, 0.1340),
            (0.3350, 0.1200), (0.3780, 0.1040), (0.4200, 0.0880), (0.4550, 0.0740)]
SK_RX = _prof(SKIRT_RX)
SK_RY = _prof(SKIRT_RY)


def build_skirt(seg=180, rows=90):
    def fn(u, v):
        # v: 0 waist -> 1 hem
        z = 0.455 - (0.455 - 0.204) * (v ** 0.94)
        rx, ry = SK_RX(z), SK_RY(z)
        ang = TAU * u
        fold = 1.0 + (0.012 + 0.030 * v) * cos(9.0 * ang + 0.6) * (0.35 + 0.65 * v)
        sx, sy = sin(ang) * fold, cos(ang) * fold
        q = 2.15
        g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** q) ** (1.0 / q)
        y = -ry * g * (1.0 if cos(ang) >= 0 else -1.0) * fold
        return (rx * sx, y, z)

    ob = C.grid("Skirt", fn, seg, rows, close_u=True)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0062, offset=1.0, even=True, rim=True)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_bodice(seg=160, rows=64):
    def fn(u, v):
        ang = TAU * u
        fw = max(0.0, cos(ang)) ** 2
        ztop = 0.5730 - 0.0135 * fw
        z = 0.4480 + (ztop - 0.4480) * v
        p = BD.torso_point(ang, z, q=2.2)
        # offset outward along the horizontal normal
        n = Vector((p.x, p.y - BD.TYC(z), 0.0))
        if n.length > 1e-6:
            n.normalize()
        off = 0.0062
        return (p.x + n.x * off, p.y + n.y * off, p.z)

    ob = C.grid("Bodice", fn, seg, rows, close_u=True)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0055, offset=1.0, even=True, rim=True)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_placket():
    """Navy centre strip with two pearl buttons."""
    zs = [0.5660, 0.5520, 0.5350, 0.5200]
    verts = []
    for z in zs:
        for sgn in (-1, 1):
            for w in (0.0, 1.0):
                pass
    # simple strip: 4 rows x 2 columns on the chest surface
    rows = []
    for z in zs:
        pts = []
        for x in (-0.0145, 0.0145):
            y = BD.torso_point(0.0, z).y
            pts.append((x, y - 0.0105, z))
        rows.append(pts)
    verts = [p for r in rows for p in r]
    faces = []
    for i in range(len(rows) - 1):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    ob = C.new_obj("Placket", verts, faces, "Maid")
    C.orient_faces(ob, 1, -1)
    C.add_solidify(ob, 0.0035, offset=1.0)
    C.shade_smooth(ob)
    return ob


def build_buttons(mats):
    objs = []
    for i, z in enumerate((0.5530, 0.5270)):
        y = BD.torso_point(0.0, z).y - 0.0125
        b = C.sphere("Button%d" % i, (0.0, y, z), (0.0068, 0.0038, 0.0068),
                     seg=32, rings=20)
        C.assign(b, mats["pearl"])
        objs.append(b)
    return objs


def build_collar(seg=150, rows=16):
    """Peter-Pan collar: hugs the neck, open at the front, two rounded points."""
    GAP = math.radians(12.0)

    def fn(uu, vv):
        ang = GAP + (TAU - 2.0 * GAP) * uu
        fw = max(0.0, cos(ang))
        pt = exp(-((abs(ang) - 0.58) / 0.27) ** 2)
        r_in = 0.0318
        r_out = 0.0645 + 0.0190 * pt + 0.0090 * fw
        r = r_in + (r_out - r_in) * vv
        z = 0.5985 - 0.0315 * (vv ** 0.86) * (0.52 + 0.48 * fw) - 0.0045 * pt * vv
        return (r * sin(ang), -0.0040 - r * cos(ang), z)

    ob = C.grid("Collar", fn, seg, rows, close_u=False)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0032, offset=0.0, even=True, rim=True)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_sleeves(mats):
    objs = []
    for side in (1, -1):
        p0 = Vector((side * 0.0860, -0.0030, 0.5610))
        p1 = Vector((side * 0.1030, -0.0240, 0.4780))
        p2 = Vector((side * 0.1150, -0.0480, 0.4460))

        def path(t):
            a = p0 * (1 - t) ** 2 + p1 * 2 * (1 - t) * t + p2 * t * t
            return a

        rad = [(0.00, 0.0400), (0.12, 0.0505), (0.28, 0.0575), (0.45, 0.0585),
               (0.62, 0.0525), (0.78, 0.0440), (0.90, 0.0370), (1.00, 0.0335)]

        def rfn(t):
            return _lerp_tab(t, rad)

        sleeve = C.tube("Sleeve", [path(i / 40) for i in range(41)],
                        [rfn(i / 40) for i in range(41)], seg=56, caps=True)
        C.add_subsurf(sleeve, 1, apply=True)
        C.shade_smooth(sleeve)
        C.assign(sleeve, mats["navy"])
        objs.append(sleeve)

        # cuff band
        c0 = path(0.952)
        c1 = path(1.045)
        cuff = C.tube("Cuff", [c0, c0 * 0.75 + c1 * 0.25, c1],
                      [0.0362, 0.0366, 0.0352], seg=56, caps=True)
        C.shade_smooth(cuff)
        C.assign(cuff, mats["white"])
        objs.append(cuff)
        # cuff button: sits ON the cuff face, oriented outward
        cc = path(1.000)
        outv = Vector((side * 0.28, -0.96, 0.0)).normalized()
        b = C.sphere("CuffBtn", (cc.x + outv.x * 0.0345, cc.y + outv.y * 0.0345,
                                 cc.z + 0.0012),
                     (0.0050, 0.0050, 0.0050), seg=24, rings=16)
        C.deform(b, lambda v: cc + (v - cc) * 0.42 + outv * 0.0012 +
                 Vector((0, 0, (v.z - cc.z) * 0.58)))
        C.shade_smooth(b)
        C.assign(b, mats["pearl"])
        objs.append(b)
    return objs


def build_shoulder_ruffle():
    """Two lace arcs sitting on the shoulder seams (not around the neck)."""
    objs = []
    for side in (1, -1):
        path = []
        n = 46
        for i in range(n):
            t = i / (n - 1)
            ang = side * (math.radians(46.0) + t * math.radians(72.0))
            z = 0.5705 + 0.0090 * math.sin(math.pi * t) - 0.0045 * t
            p = BD.torso_point(ang, z, q=2.2)
            nrm = Vector((p.x, p.y - BD.TYC(z), 0.0))
            if nrm.length > 1e-6:
                nrm.normalize()
            path.append((p.x + nrm.x * 0.0045, p.y + nrm.y * 0.0045, p.z + 0.0015))
        ob = RF.build_ruffle("ShoulderRuffle%s" % side, path=path, up=(0, 0, 1),
                             width=0.0255, scallops=8, amp=0.0052, pleat=0.0014,
                             thickness=0.0020, flare=0.55, closed=False,
                             style="scallop")
        objs.append(ob)
    return objs


# ================================================================== apron
def _apron_angle(v):
    return radians(20.0 + 19.0 * (v ** 1.02))


def _apron_hem_z(u):
    au = abs(u)
    return P.Z_APRON_HEM + 0.062 * max(0.0, au - 0.72) ** 2 / 0.0784


_APRON_HW = [(0.2430, 0.1370), (0.2650, 0.1300), (0.2900, 0.1215),
             (0.3300, 0.1120), (0.3700, 0.1015), (0.4100, 0.0920),
             (0.4320, 0.0898), (0.4550, 0.0800), (0.4700, 0.0710),
             (0.5000, 0.0652), (0.5290, 0.0620)]


def _apron_hw(z):
    z = max(_APRON_HW[-1][0], min(_APRON_HW[0][0], z))
    for i in range(len(_APRON_HW) - 1):
        if _APRON_HW[i][0] >= z >= _APRON_HW[i + 1][0]:
            f = (_APRON_HW[i][0] - z) / (_APRON_HW[i][0] - _APRON_HW[i + 1][0])
            f = f * f * (3 - 2 * f)
            return _APRON_HW[i][1] * (1 - f) + _APRON_HW[i + 1][1] * f
    return _APRON_HW[-1][1]


def _apron_point(u, v):
    """v 0 = bib top (z .529), 1 = hem (z .259); one continuous surface."""
    z = 0.5290 - (0.5290 - 0.2430) * (v ** 0.94)
    # rounded bottom corners
    z += 0.026 * max(0.0, abs(u) - 0.78) ** 2 / 0.0484 * (v ** 2)
    hw = _apron_hw(z) * u
    band = C.smoothstep(0.4550, 0.4480, z) * (1.0 - C.smoothstep(0.4370, 0.4320, z))
    if z >= 0.4480:
        rx = max(1e-4, BD.TRX(min(0.604, z)))
        ang = asin(max(-0.995, min(0.995, hw / rx)))
        p = BD.torso_point(ang, z, q=2.2)
        n = Vector((p.x, p.y - BD.TYC(z), 0.0)).normalized()
        off = 0.0130 + 0.0040 * band
        return (p.x + n.x * off, p.y + n.y * off, z)
    rx, ry = SK_RX(z), SK_RY(z)
    ang = asin(max(-0.995, min(0.995, hw / max(1e-4, rx))))
    foldk = 1.0 + (0.010 + 0.024 * C.smoothstep(0.44, 0.28, z)) * \
        cos(5.0 * u + 0.6) * (0.35 + 0.65 * (1.0 - v))
    g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** 2.15) ** (1.0 / 2.15)
    x = rx * sin(ang) * foldk
    y = -ry * g * foldk
    n = Vector((x, y, 0.0)).normalized()
    off = 0.0125 + 0.0040 * band
    return (x + n.x * off, y + n.y * off, z)


def build_apron_body(rows=80, cols=68):
    def fn(uu, vv):
        u = uu * 2.0 - 1.0
        return _apron_point(u, vv)

    ob = C.grid("ApronBody", fn, cols, rows, close_u=False)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0032, offset=0.0, even=True, rim=True)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_apron_ruffle_one():
    """Scalloped trim following the whole outer border of the one-piece apron."""
    path = []
    nside, nhem = 30, 76
    for i in range(nside):
        v = 1.0 - (i / (nside - 1)) * 0.985
        path.append(_apron_point(1.0, v))
    for i in range(1, nhem):
        path.append(_apron_point(1.0 - 2.0 * i / nhem, 1.0))
    for i in range(nside):
        v = 0.015 + (i / (nside - 1)) * 0.985
        path.append(_apron_point(-1.0, v))
    nrm = []
    hips = []
    for p in path:
        hips.append(p)
    ob = RF.build_ruffle("ApronRuffle", path=path, up=(0, 0, 1),
                         width=0.0175, scallops=26, amp=0.0058, pleat=0.0012,
                         thickness=0.0020, flare=0.45, closed=False, style="scallop")
    return ob


def build_apron_straps_one():
    """Straps as part of the apron object (still separate shells, joined later)."""
    objs = []
    for side in (1, -1):
        ctrl = [(side * 0.0620, 0.5320), (side * 0.0640, 0.5500),
                (side * 0.0620, 0.5680), (side * 0.0480, 0.5770),
                (side * 0.0300, 0.5750)]
        pts = []
        for (x, z) in ctrl:
            rx = max(1e-4, BD.TRX(min(0.604, z)))
            ang = asin(max(-0.995, min(0.995, x / rx)))
            p = BD.torso_point(ang, z, q=2.2)
            n = Vector((p.x, p.y - BD.TYC(z), 0.0)).normalized()
            off = 0.0140
            pts.append((p.x + n.x * off, p.y + n.y * off, p.z))
        pts = C.polyline_resample(pts, 26)
        objs.append(_strap("ApronStrap%s" % side, pts, 0.0105, 0.0024))
    return objs


def build_apron_skirt(rows=40, cols=64):
    def fn(u, v):
        # u: 0..1 across -> -1..1, v: 0 waistband -> 1 hem
        uu = u * 2.0 - 1.0
        ang = uu * _apron_angle(v)
        z = 0.4500 - (0.4500 - _apron_hem_z(uu)) * (v ** 0.94)
        rx, ry = SK_RX(z), SK_RY(z)
        q = 2.15
        g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** q) ** (1.0 / q)
        fold = 1.0 + (0.012 + 0.030 * v) * cos(9.0 * ang + 0.6) * (0.35 + 0.65 * v)
        x = rx * sin(ang) * fold
        y = -ry * g * fold * (1.0 if cos(ang) >= 0 else -1.0)
        off = 0.0110
        n = Vector((x, y, 0)).normalized()
        return (x + n.x * off, y + n.y * off, z)

    ob = C.grid("ApronSkirt", fn, cols, rows, close_u=False)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0030, offset=0.0)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def build_waistband():
    rows = 8
    cols = 160
    verts = []
    for j in range(rows + 1):
        v = j / rows
        z = 0.4605 - 0.0300 * v
        for i in range(cols):
            ang = TAU * i / cols
            rx, ry = SK_RX(z) * 1.012, SK_RY(z) * 1.012
            q = 2.15
            g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** q) ** (1.0 / q)
            verts.append((rx * sin(ang), -ry * g * (1.0 if cos(ang) >= 0 else -1.0), z))
    faces = []
    for j in range(rows):
        for i in range(cols):
            i2 = (i + 1) % cols
            a = j * cols + i
            b = j * cols + i2
            faces.append((a, b, b + cols, a + cols))
    ob = C.new_obj("Waistband", verts, faces, "Maid")
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0040, offset=1.0)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)
    return ob


def _apron_border_point(u, v):
    ang = u * _apron_angle(v)
    z = 0.4500 - (0.4500 - _apron_hem_z(u)) * (v ** 0.94)
    rx, ry = SK_RX(z), SK_RY(z)
    g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** 2.15) ** (1 / 2.15)
    x = rx * sin(ang)
    y = -ry * g
    nn = Vector((x, y, 0)).normalized()
    return (x + nn.x * 0.0120, y + nn.y * 0.0120, z)


def build_apron_ruffle():
    """Scalloped trim following the apron border (right edge, hem, left edge)."""
    path = []
    nside = 34
    nhem = 70
    for i in range(nside):
        v = 1.0 - (i / (nside - 1)) * 0.975
        path.append(_apron_border_point(1.0, v))
    for i in range(1, nhem):
        path.append(_apron_border_point(1.0 - 2.0 * i / nhem, 1.0))
    for i in range(nside):
        v = 0.025 + (i / (nside - 1)) * 0.975
        path.append(_apron_border_point(-1.0, v))
    ob = RF.build_ruffle("ApronRuffle", path=path, up=(0, 0, 1),
                         width=0.0125, scallops=30, amp=0.0038, pleat=0.0010,
                         thickness=0.0020, flare=0.40, closed=False, style="scallop")
    return ob


def _strap(name, pts, w=0.0105, t=0.0022):
    """Flat strap hugging the body: width across the surface, thickness outward."""
    P = [Vector(p) for p in pts]
    n = len(P)
    verts = []
    for i in range(n):
        if i == 0:
            tg = P[1] - P[0]
        elif i == n - 1:
            tg = P[-1] - P[-2]
        else:
            tg = P[i + 1] - P[i - 1]
        tg.normalize()
        out = Vector((P[i].x, P[i].y, 0.0))
        if out.length < 1e-6:
            out = Vector((0, -1, 0))
        out.normalize()
        bz = C.smoothstep(0.5480, 0.5790, P[i].z)
        out = (out * (1.0 - bz) + Vector((0.0, 0.0, 1.0)) * bz).normalized()
        side = tg.cross(out).normalized()
        for (dv, dn) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            verts.append(tuple(P[i] + side * (w * dv) + out * (t * 0.5 * dn + 0.0005 * dn)))
    faces = []
    for i in range(n - 1):
        a = i * 4
        b = (i + 1) * 4
        faces.append((a + 0, a + 1, b + 1, b + 0))
        faces.append((a + 2, b + 2, b + 3, a + 3))
        faces.append((a + 0, b + 0, b + 2, a + 2))
        faces.append((a + 1, a + 3, b + 3, b + 1))
    faces.append((0, 1, 3, 2))
    e = (n - 1) * 4
    faces.append((e + 0, e + 2, e + 3, e + 1))
    ob = C.new_obj(name, verts, faces, "Maid")
    C.recalc_normals(ob)
    C.shade_smooth(ob)
    C.shade_smooth(ob, 46)
    return ob


def _body_point(x, z, off=0.0135, q=2.2):
    rx = max(1e-4, BD.TRX(min(0.604, max(0.332, z))))
    ang = asin(max(-0.995, min(0.995, x / rx)))
    p = BD.torso_point(ang, z, q=q)
    n = Vector((p.x, p.y - BD.TYC(z), 0.0)).normalized()
    return (p.x + n.x * off, p.y + n.y * off, p.z)


def build_apron_straps():
    """Bib corner -> over the shoulder -> cross at mid back -> waistband (X)."""
    objs = []
    for side in (1, -1):
        ctrl = [
            (0.0640, -0.0885, 0.5320),
            (0.0680, -0.0790, 0.5510),
            (0.0740, -0.0480, 0.5710),
            (0.0755, -0.0100, 0.5795),
            (0.0700, 0.0290, 0.5770),
            (0.0500, 0.0640, 0.5560),
            (0.0200, 0.0800, 0.5160),
            (-0.0150, 0.0845, 0.4820),
            (-0.0430, 0.0855, 0.4600),
            (-0.0530, 0.0855, 0.4520),
        ]
        pts = [(side * x, y, z) for (x, y, z) in ctrl]
        pts = C.polyline_resample(pts, 54)
        objs.append(_strap("Strap%s" % side, pts, 0.0120, 0.0019))
    return objs


def build_back_straps():
    return []


def build_bow(mats):
    ob = BW.build_bow("BackBow", location=(0.0, 0.0790, 0.4470),
                      rotation=(0.0, 0.0, math.pi), width=0.124, loop_h=0.046,
                      ribbon_w=0.0225, thickness=0.0019, tails=2, tail_len=0.082,
                      tail_spread=0.052, tail_notch=0.0070, loop_twist=0.55,
                      droop=0.32, knot_w=0.018, knot_h=0.017)
    C.assign(ob, mats["satin"])
    return ob


# ================================================================== headband
def _headband_path(n=140, half_deg=105.0):
    """Open crescent: front centre high on the crown, free ends behind the temples."""
    import mhair as HR
    path = []
    for i in range(n):
        t = i / (n - 1)
        a = math.radians(-half_deg + 2.0 * half_deg * t)     # 0 = front centre
        k = abs(a) / math.radians(half_deg)
        z = 0.9370 - 0.0615 * (1.0 - math.cos(math.pi * k))   # smooth skull arc
        zc = min(0.9640, max(0.6150, z))
        q = HR.hair_point(a, zc, 0.0020)
        path.append(Vector((q.x, q.y, q.z)))
    return path


def build_headband(mats):
    """Crescent headdress: 0.014 wide ribbon + gathered petal frill, open at the back."""
    path = _headband_path(140, 105.0)
    n = len(path)
    band_w = 0.0210
    # ---- band ribbon (strip below the path) ----
    verts = []
    for p in path:
        verts.append(tuple(p))
    for p in path:
        d = Vector((p.x, p.y, 0.0))
        d = d.normalized() if d.length > 1e-6 else Vector((0, -1, 0))
        q = p - Vector((0, 0, band_w))
        verts.append((q.x, q.y, q.z))
    faces = []
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))
    band = C.new_obj("Headband", verts, faces, "Maid")
    C.recalc_normals(band)
    C.add_solidify(band, 0.0030, offset=0.0)
    C.add_subsurf(band, 1, apply=True)
    C.shade_smooth(band)
    C.assign(band, mats["white"])

    # ---- gathered petal frill (11 lobes over the arc) ----
    lobes = 11.0
    rows = 8
    verts = []
    for i in range(n):
        p = path[i]
        pn = path[min(n - 1, i + 1)]
        pp = path[max(0, i - 1)]
        tg = (pn - pp).normalized()
        rad = Vector((p.x, p.y, 0.0))
        rad = rad.normalized() if rad.length > 1e-6 else Vector((0, -1, 0))
        up = rad.cross(tg).normalized()
        if up.z < 0:
            up = -up
        t = i / (n - 1)
        # taper the frill to nothing at the two free ends
        ends = C.smoothstep(0.0, 0.10, t) * (1.0 - C.smoothstep(0.90, 1.0, t))
        ph = 0.5 + 0.5 * math.cos(TAU * lobes * t + 0.4)
        petal = ph ** 0.62
        for j in range(rows + 1):
            f = j / rows
            w = (0.0105 + 0.0115 * petal) * (f ** 0.74) * ends
            h = (0.0300 + 0.0075 * petal) * (f ** 0.62) * ends
            h += 0.0014 * math.sin(TAU * 6.0 * t) * (f ** 2) * ends
            q = p + rad * w + up * h
            verts.append(tuple(q))
    faces = []
    for i in range(n - 1):
        for j in range(rows):
            a = i * (rows + 1) + j
            b = (i + 1) * (rows + 1) + j
            faces.append((a, b, b + 1, a + 1))
    frill = C.new_obj("HeadbandRuffle", verts, faces, "Maid")
    C.recalc_normals(frill)
    C.add_solidify(frill, 0.0024, offset=0.0, even=True, rim=True)
    C.add_subsurf(frill, 1, apply=True)
    C.shade_smooth(frill)
    C.assign(frill, mats["white"])
    return [band, frill]


# ================================================================== underwear
def build_panties(seg=144, rows=44):
    """Briefs measured from the sheet: waist 0.345, crotch 0.195, hip w 0.230,
    leg-hole top 0.283, 0.015 elasticated band, diagonal leg openings."""
    Z_WAIST, Z_CROTCH, Z_LEGTOP = 0.3450, 0.1950, 0.2830
    W_HIP = 0.0930
    D_HIP = 0.0800

    def leg_z(ang):
        # 0 at the front centre (crotch), high at 90 deg (leg hole), low again at back
        c = abs(cos(ang))
        return Z_CROTCH + (Z_LEGTOP - Z_CROTCH) * (1.0 - c ** 1.55)

    def fn(u, v):
        ang = TAU * u
        zb = leg_z(ang)
        z = Z_WAIST + (zb - Z_WAIST) * (v ** 0.88)
        # hips bulge at ~42% down the garment, then taper to the crotch
        t = (Z_WAIST - z) / max(1e-5, (Z_WAIST - Z_CROTCH))
        bulge = 1.0 + 0.045 * (1.0 - (t - 0.42) ** 2 / 0.34)
        rx = W_HIP * bulge
        ry = D_HIP * bulge
        # narrow toward the crotch panel
        narrow = 1.0 - 0.50 * C.smoothstep(0.58, 1.0, t)
        rx *= narrow
        ry *= narrow
        q = 2.2
        g = max(0.0, 1.0 - min(1.0, abs(sin(ang))) ** q) ** (1.0 / q)
        return (rx * sin(ang), -ry * g * (1.0 if cos(ang) >= 0 else -1.0), z)

    ob = C.grid("Panties", fn, seg, rows, close_u=True)
    C.recalc_normals(ob)
    C.add_solidify(ob, 0.0032, offset=1.0)
    C.add_subsurf(ob, 1, apply=True)
    C.shade_smooth(ob)

    # ---- crotch gusset: closes the garment so nothing is exposed ----
    def gfn(uu, vv):
        x = -0.0345 + 0.0690 * uu
        y = -0.0640 + 0.1280 * vv
        k = (x / 0.0345) ** 2
        z = 0.1935 + 0.0125 * k * 0.55 + 0.0070 * (abs(vv - 0.5) * 2.0)
        return (x, y, z)

    g = C.grid("PantiesGusset", gfn, 28, 16, close_u=False)
    C.recalc_normals(g)
    C.add_solidify(g, 0.0034, offset=1.0, even=True, rim=True)
    C.add_subsurf(g, 1, apply=True)
    C.shade_smooth(g)
    return C.join_objs([ob, g], "Panties")


def _leg_r(z):
    """Same leg profile as mbody so the sock hugs the calf."""
    t = (0.400 - z) / 0.352
    tab = [(0.00, 0.0430), (0.18, 0.0400), (0.38, 0.0330), (0.55, 0.0290),
           (0.70, 0.0305), (0.85, 0.0235), (0.95, 0.0180), (1.00, 0.0175)]
    t = max(0.0, min(1.0, t))
    for i in range(len(tab) - 1):
        if tab[i][0] <= t <= tab[i + 1][0]:
            f = (t - tab[i][0]) / (tab[i + 1][0] - tab[i][0])
            f = f * f * (3 - 2 * f)
            return tab[i][1] * (1 - f) + tab[i + 1][1] * f
    return tab[-1][1]


def _sock_center(side, z):
    t = (0.400 - z) / 0.352
    x = side * (0.0475 - 0.0035 * C.smoothstep(0.55, 1.0, t))
    y = -0.004 + 0.010 * C.smoothstep(0.55, 1.0, t)
    return Vector((x, y, z))


def _sock_r(z):
    """Sock = leg surface + 1.5 mm, no bulk, tapering with the calf to the ankle."""
    calf = _leg_r(z) + 0.0052
    if z >= 0.0900:
        return calf
    f = C.smoothstep(0.0900, 0.0550, z)
    return calf * (1 - f) + 0.0252 * f


def build_socks(mats):
    """Plain white knee socks: no rib, no band, no second line (per reference)."""
    objs = []
    for side in (1, -1):
        ztop, zbot = 0.1780, 0.0280
        n = 60
        pts, rs = [], []
        for i in range(n):
            t = i / (n - 1)
            z = ztop - (ztop - zbot) * t
            pts.append(_sock_center(side, z))
            rs.append(_sock_r(z))
        ob = C.tube("Sock", pts, rs, seg=52, caps=True)
        C.add_subsurf(ob, 1, apply=True)
        C.shade_smooth(ob)
        C.assign(ob, mats["sock"])
        objs.append(ob)
        # rolled rim only: 1.2 mm proud, 4 mm tall
        c0 = _sock_center(side, ztop + 0.0004)
        c1 = _sock_center(side, ztop - 0.0042)
        rim = C.tube("SockRim", [c0, _sock_center(side, ztop - 0.0020), c1],
                     [_sock_r(ztop) + 0.0009, _sock_r(ztop) + 0.0016,
                      _sock_r(ztop) - 0.0002], seg=52, caps=True)
        C.add_subsurf(rim, 1, apply=True)
        C.shade_smooth(rim)
        C.assign(rim, mats["sock"])
        objs.append(rim)
    return objs


def build_shoes(mats):
    objs = []
    for side, sx in (("R", -0.0468), ("L", 0.0468)):
        up, sole = SH.build_loafer("Loafer" + side, side=side,
                                   length=0.1550, width=0.0700, height=0.0705,
                                   sole_h=0.0115, toe_rise=0.0280,
                                   strap=True, strap_w=0.0130, strap_y=-0.0200,
                                   origin=(sx, 0.0040, 0.0))
        for o in (up, sole):
            if o is not None:
                C.shade_smooth(o)
        # client-tuned fit (kept verbatim so a rebuild matches their session)
        _TR = {"L": ((-0.00714, 0.0, 0.0), (1.15449, 1.03258, 1.0)),
               "R": ((0.00682, 0.00258, 0.0), (1.15400, 1.0, 1.0))}
        _loc, _scl = _TR[side]
        for o in (up, sole):
            if o is not None:
                o.location = _loc
                o.scale = _scl
        C.assign(up, mats["leather"])
        if sole is not None:
            C.assign(sole, mats["sole"])
            objs.append(sole)
        objs.append(up)
    return objs


# ================================================================== assembly
def build_outfit(mats):
    out = {}
    out["skirt"] = build_skirt()
    out["bodice"] = build_bodice()
    out["placket"] = build_placket()
    out["collar"] = build_collar()
    out["shoulder_ruffle"] = build_shoulder_ruffle()
    out["back_straps"] = build_back_straps()
    out["sleeves"] = build_sleeves(mats)
    out["buttons"] = build_buttons(mats)
    out["bow"] = build_bow(mats)
    out["headband"] = build_headband(mats)
    out["panties"] = build_panties()
    out["socks"] = build_socks(mats)
    out["shoes"] = build_shoes(mats)

    C.assign(out["skirt"], mats["navy"])
    C.assign(out["bodice"], mats["navy"])
    C.assign(out["placket"], mats["navy"])
    C.assign(out["collar"], mats["white"])
    for o in out["shoulder_ruffle"]:
        C.assign(o, mats["white"])
    for o in out["back_straps"]:
        C.assign(o, mats["white"])
    C.assign(out["panties"], mats["sock"])

    # ---------------- apron: ONE object (body + sash + straps + ruffle) ----
    parts = [build_apron_body(), build_waistband(), build_apron_ruffle_one()]
    parts += build_apron_straps_one()
    for o in parts:
        C.assign(o, mats["white"])
    apron = C.join_objs(parts, "Apron")
    C.shade_smooth(apron)
    out["apron"] = apron
    return out
