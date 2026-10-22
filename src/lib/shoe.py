"""shoe.py -- procedural chibi penny loafer.

Meters.  Character height 1.0.  Ankle centre (0, 0, 0.055).  Foot forward -Y,
up +Z, sole bottom at z = 0.

    build_loafer(...) -> (upper, sole)

Topology
--------
upper : one continuous tube lofted from the welt loop (footprint) up to the
        collar rim.  The rim is an open circular-ish loop (radius ~0.033),
        so a sock / leg enters it.  The rim edge is folded over into a thin
        rolled collar lip (still open -- the lip's inner edge is the aperture).
        A penny strap + keeper are swept on the vamp and joined into the same
        object as separate shells.
sole  : closed slab following the footprint + welt margin, walkable flat
        bottom, rounded welt lip, crisp notch at the heel.
"""

import math

import bpy

__all__ = ["build_loafer"]

# --------------------------------------------------------------- resolution
N_SIDE = 192      # segments around the shoe          (spec: >= 48)
N_PROF = 60       # profile rings welt -> collar rim  (spec: >= 40)
N_LIP = 4         # extra rings of the rolled collar lip
N_SOLE = 192      # sole segments around
N_STRAP = 96      # samples along the strap band
N_BAND = 16       # points around the strap cross-section
N_KEEP = 56       # samples along the keeper ridge
N_KEEPCI = 12     # points around the keeper cross-section

_TWO_PI = 2.0 * math.pi


# --------------------------------------------------------------- small math
def _clamp(x, a, b):
    return a if x < a else (b if x > b else x)


def _smoothstep(a, b, x):
    if a == b:
        return 0.0 if x < a else 1.0
    t = _clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hypot(a, b):
    return math.sqrt(a * a + b * b)


class _Curve(object):
    """Monotone cubic Hermite (Fritsch-Carlson) through (xs, ys)."""

    def __init__(self, xs, ys):
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError("_Curve needs matching xs/ys")
        self.xs = [float(v) for v in xs]
        self.ys = [float(v) for v in ys]
        n = len(self.xs)
        h = [self.xs[i + 1] - self.xs[i] for i in range(n - 1)]
        d = [(self.ys[i + 1] - self.ys[i]) / h[i] for i in range(n - 1)]
        m = [0.0] * n
        m[0] = d[0]
        m[-1] = d[-1]
        for i in range(1, n - 1):
            if d[i - 1] * d[i] <= 0.0:
                m[i] = 0.0
            else:
                w1 = 2.0 * h[i] + h[i - 1]
                w2 = h[i] + 2.0 * h[i - 1]
                m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
        self.h = h
        self.m = m

    def __call__(self, x):
        xs = self.xs
        if x <= xs[0]:
            return self.ys[0]
        if x >= xs[-1]:
            return self.ys[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        t = (x - xs[lo]) / self.h[lo]
        t2 = t * t
        t3 = t2 * t
        y0 = self.ys[lo]
        y1 = self.ys[lo + 1]
        m0 = self.m[lo] * self.h[lo]
        m1 = self.m[lo + 1] * self.h[lo]
        return ((2.0 * t3 - 3.0 * t2 + 1.0) * y0 + (t3 - 2.0 * t2 + t) * m0
                + (-2.0 * t3 + 3.0 * t2) * y1 + (t3 - t2) * m1)


# shape of the cross-section profile, normalised (0 at welt, 1 at rim).
# fast rise -> long plateau (toe box crest) -> vamp rise to the collar.
_TOE_SHAPE = _Curve(
    [0.00, 0.12, 0.26, 0.40, 0.54, 0.68, 0.82, 1.00],
    [0.00, 0.34, 0.66, 0.88, 0.98, 1.00, 0.995, 1.00],
)

# horizontal run from welt to rim, normalised.
_GPROF = _Curve(
    [0.00, 0.08, 0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.88, 1.00],
    [0.00, 0.012, 0.050, 0.155, 0.295, 0.455, 0.625, 0.785, 0.925, 1.00],
)


# ------------------------------------------------------------- 2-d helpers
def _polyline(pts):
    """closed polyline -> per-vertex unit outward normal (CCW loop)."""
    n = len(pts)
    out = []
    for i in range(n):
        a = pts[i - 1]
        b = pts[(i + 1) % n]
        tx = b[0] - a[0]
        ty = b[1] - a[1]
        L = _hypot(tx, ty) or 1.0
        out.append((ty / L, -tx / L))
    return out


def _arc_table(pts):
    n = len(pts)
    cum = [0.0]
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        cum.append(cum[-1] + _hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def _resample_closed(pts, n_out):
    """resample a closed polyline to n_out points, evenly by arc length."""
    n = len(pts)
    cum = _arc_table(pts)
    total = cum[-1]
    if total <= 1e-12:
        return list(pts)
    step = total / n_out
    out = []
    j = 0
    for k in range(n_out):
        target = k * step
        while j < n - 1 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg <= 1e-15 else (target - cum[j]) / seg
        a = pts[j]
        b = pts[(j + 1) % n]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _ellipse_radius(c, s, rx, ry):
    """radius of the ellipse (rx,ry) in direction (c,s)."""
    d = _hypot(c / rx, s / ry)
    return 1.0 / d if d > 1e-12 else 0.0


def _sgn_pow(v, p):
    if v >= 0.0:
        return v ** p
    return -((-v) ** p)


def _sweep_profile(pts, nrms, tans, prof):
    """Sweep a 2-d (b,n) profile along a path.

    pts/nrms/tans : lists of 3-tuples (position, outward normal, path tangent)
    prof          : list of (b, n) pairs, CCW around +tangent
                    or callable(i) -> such a list (per path sample)
    returns (verts, faces) with outward-facing winding.
    """
    npath = len(pts)
    prof0 = prof(0) if callable(prof) else prof
    m = len(prof0)
    verts = []
    for i in range(npath):
        p = pts[i]
        t = tans[i]
        nn = nrms[i]
        pr = prof(i) if callable(prof) else prof
        # frame: t, n, b = n x t  (right handed b,n,t)
        bb = (nn[1] * t[2] - nn[2] * t[1],
              nn[2] * t[0] - nn[0] * t[2],
              nn[0] * t[1] - nn[1] * t[0])
        for (b, h) in pr:
            verts.append((p[0] + bb[0] * b + nn[0] * h,
                          p[1] + bb[1] * b + nn[1] * h,
                          p[2] + bb[2] * b + nn[2] * h))
    faces = []
    for i in range(npath - 1):
        i0 = i * m
        i1 = (i + 1) * m
        for j in range(m):
            j1 = (j + 1) % m
            faces.append((i0 + j, i0 + j1, i1 + j1, i1 + j))
    # caps
    c0 = len(verts)
    p0 = pts[0]
    verts.append((p0[0] + nrms[0][0] * 0.0, p0[1] + nrms[0][1] * 0.0, p0[2] + nrms[0][2] * 0.0))
    for j in range(m):
        j1 = (j + 1) % m
        faces.append((c0, j1, j))
    c1 = len(verts)
    p1 = pts[-1]
    verts.append((p1[0], p1[1], p1[2]))
    base = (npath - 1) * m
    for j in range(m):
        j1 = (j + 1) % m
        faces.append((c1, base + j, base + j1))
    return verts, faces


# ---------------------------------------------------------------- builder
def _build_core(length, width, height, sole_h, toe_rise,
                strap, strap_w, strap_y, toe_round):
    """Build one right-hand loafer at the origin.  -> dict of (verts, faces)."""

    # ---- overall scalars ------------------------------------------------
    toe_y = -0.6775 * length            # -0.1050 at length 0.155
    heel_y = 0.3225 * length            # +0.0500
    w_sole = 0.5 * width                # 0.0350
    z_welt = sole_h - _clamp(sole_h * 0.18, 0.0012, 0.0022)
    rim_drop_front = 0.075 * height     # topline height at the throat (raised: loafer covers the instep)
    rim_side_dip = 0.0625 * height      # extra dip at the sides
    rim_rx = 0.3571 * width             # 0.0250
    rim_ry = 0.2039 * length            # 0.0316
    rim_cx = 0.0
    rim_cy = 0.005
    lip_in = 0.00090                    # how far the collar edge folds in
    lip_drop = 0.00240
    groove_depth = 0.00115 * (sole_h / 0.0105)
    groove_z0 = 0.372 * sole_h
    groove_z1 = 0.480 * sole_h

    # ---- sole outline (this one owns the spec bbox) ---------------------
    m_dense = 2048
    dense = []
    n_exp = 2.75
    for k in range(m_dense):
        t = _TWO_PI * k / m_dense
        c = math.cos(t)
        s = math.sin(t)
        y = 0.5 * (toe_y + heel_y) - 0.5 * (heel_y - toe_y) * c
        x = w_sole * ((1.0 - abs(c) ** n_exp) ** (1.0 / n_exp)) * (1.0 if s >= 0 else -1.0)
        dense.append((x, y))
    SOLE = _resample_closed(dense, N_SOLE)
    SOLE_N = _polyline(SOLE)

    # ---- welt margin (lateral side beefier => asymmetrical shoe) --------
    m_of = []
    for i in range(N_SOLE):
        x, y = SOLE[i]
        lat = _clamp(-x / max(w_sole, 1e-6), -1.0, 1.0)      # +1 on the lateral side
        toe_f = _smoothstep(-0.02, -0.06, y)
        heel_f = _smoothstep(0.010, 0.046, y)
        m = (0.00135 + 0.00055 * toe_f + 0.00020 * heel_f) * (1.04 + 0.26 * lat)
        m_of.append(m)

    # ---- upper footprint = sole outline pulled in by the welt margin ----
    FP = []
    for i in range(N_SOLE):
        m = m_of[i]
        FP.append((SOLE[i][0] - SOLE_N[i][0] * m,
                   SOLE[i][1] - SOLE_N[i][1] * m))
    FP = _resample_closed(FP, N_SIDE)
    FP_N = _polyline(FP)
    FP_LAT = [_clamp(-p[0] / max(w_sole, 1e-6), -1.0, 1.0) for p in FP]

    # ---- collar rim (radial projection of the welt onto an ellipse) -----
    RM = []
    ZR = []
    for i in range(N_SIDE):
        dx = FP[i][0] - rim_cx
        dy = FP[i][1] - rim_cy
        L = _hypot(dx, dy) or 1.0
        cx = dx / L
        cy = dy / L
        r = _ellipse_radius(cx, cy, rim_rx, rim_ry)
        RM.append((rim_cx + cx * r, rim_cy + cy * r))
        # topline: lowest at the throat (front), highest at the heel counter
        front = _clamp((rim_cy - RM[-1][1]) / rim_ry, -1.0, 1.0)
        ZR.append(height - rim_drop_front * 0.5 * (1.0 + front)
                  - rim_side_dip * (1.0 - front * front))

    # ---- profile fractions ---------------------------------------------
    crest_z = sole_h + toe_rise * toe_round
    fp = _clamp((crest_z - z_welt) / max(ZR[0] - z_welt, 1e-5), 0.22, 0.78)

    def fprof(v):
        if v <= 0.60:
            return fp * _TOE_SHAPE(v / 0.60)
        u = (v - 0.60) / 0.40
        return fp + (1.0 - fp) * (u ** 2.2)

    _BA, _BP, _BQ = 0.25, 0.80, 2.1
    _bmax = max(((t / 200.0 / _BA) ** _BP) * (((1.0 - t / 200.0) / (1.0 - _BA)) ** _BQ)
                for t in range(1, 200))

    def bprof(v):
        """soft leather bulge over the welt: peaks low, dies at welt and rim"""
        v = _clamp(v, 0.0, 1.0)
        if v <= 0.0 or v >= 1.0:
            return 0.0
        return (((v / _BA) ** _BP) * (((1.0 - v) / (1.0 - _BA)) ** _BQ)) / _bmax

    V = [k / (N_PROF - 1.0) for k in range(N_PROF)]
    G = [_GPROF(v) for v in V]
    F = [fprof(v) for v in V]
    B = [bprof(v) for v in V]

    bamp = [0.00165 * (0.78 + 0.22 * FP_LAT[i]) for i in range(N_SIDE)]

    # ---- the surface ----------------------------------------------------
    def surf(i, v, gi=None, fi=None, bi=None):
        i %= N_SIDE
        bx, by = FP[i]
        tx, ty = RM[i]
        g = _GPROF(v) if gi is None else gi
        f = fprof(v) if fi is None else fi
        b = bprof(v) if bi is None else bi
        x = bx + (tx - bx) * g
        y = by + (ty - by) * g
        z = z_welt + (ZR[i] - z_welt) * f
        k = bamp[i] * b
        return (x + FP_N[i][0] * k, y + FP_N[i][1] * k, z)

    # ---- upper grid ------------------------------------------------------
    rings = []          # rings[k] = list of xyz, k = 0..N_PROF+N_LIP-1
    for k in range(N_PROF):
        rings.append([surf(i, V[k], G[k], F[k], B[k]) for i in range(N_SIDE)])
    for m in range(1, N_LIP + 1):
        t = m / float(N_LIP)
        scale = 1.0 - (lip_in / max(rim_rx, 1e-6)) * (t ** 1.15)
        dz = -lip_drop * (t ** 1.25)
        ring = []
        for i in range(N_SIDE):
            rx = rim_cx + (RM[i][0] - rim_cx) * scale
            ry = rim_cy + (RM[i][1] - rim_cy) * scale
            ring.append((rx, ry, ZR[i] + dz))
        rings.append(ring)

    uverts = []
    for ring in rings:
        uverts.extend(ring)
    ufaces = []
    for k in range(len(rings) - 1):
        for i in range(N_SIDE):
            i1 = (i + 1) % N_SIDE
            a = k * N_SIDE + i
            b = k * N_SIDE + i1
            c = (k + 1) * N_SIDE + i1
            d = (k + 1) * N_SIDE + i
            ufaces.append((a, b, c, d))

    # ---- strap + keeper --------------------------------------------------
    if strap:
        y_s = strap_y
        # must sit on the vamp, in front of the throat
        y_throat = rim_cy - rim_ry
        y_max = y_throat - strap_w * 0.5 - 0.0030
        y_s = min(y_s, y_max)
        # index where the welt reaches that y (front arc)
        i_max = 0
        for i in range(N_SIDE // 2):
            if FP[i][1] <= y_s:
                i_max = i
            else:
                break
        if i_max >= 6:
            pts = []
            nrms = []
            for ii in list(range(-i_max, i_max + 1)):
                i = ii % N_SIDE
                by = FP[i][1]
                ty = RM[i][1]
                den = ty - by
                q = 0.0 if abs(den) < 1e-9 else (y_s - by) / den
                q = _clamp(q, 0.0, 1.0)
                # invert G (monotone) for v
                lo, hi = 0, N_PROF - 1
                if q <= G[0]:
                    v = 0.0
                elif q >= G[-1]:
                    v = 1.0
                else:
                    while hi - lo > 1:
                        mid = (lo + hi) // 2
                        if G[mid] <= q:
                            lo = mid
                        else:
                            hi = mid
                    span = G[hi] - G[lo]
                    frac = 0.0 if span < 1e-12 else (q - G[lo]) / span
                    v = (lo + frac) / (N_PROF - 1.0)
                p = surf(i, v)
                # surface normal from parametric derivatives
                im = (i - 1) % N_SIDE
                ip = (i + 1) % N_SIDE
                pa = surf(im, v)
                pb = surf(ip, v)
                vlo = max(0.0, v - 0.012)
                vhi = min(1.0, v + 0.012)
                if vhi - vlo < 1e-6:
                    vhi = min(1.0, vlo + 0.012)
                pc = surf(i, vlo)
                pd = surf(i, vhi)
                ax = pb[0] - pa[0]; ay = pb[1] - pa[1]; az = pb[2] - pa[2]
                bx2 = pd[0] - pc[0]; by2 = pd[1] - pc[1]; bz2 = pd[2] - pc[2]
                nx = ay * bz2 - az * by2
                ny = az * bx2 - ax * bz2
                nz = ax * by2 - ay * bx2
                nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                pts.append(p)
                nrms.append((nx / nl, ny / nl, nz / nl))

            # resample the path evenly by arc length
            cum = [0.0]
            for i in range(1, len(pts)):
                a = pts[i - 1]
                b = pts[i]
                cum.append(cum[-1] + math.dist(a, b))
            total = cum[-1]
            if total > 1e-6:
                newp = []
                newn = []
                j = 0
                for k in range(N_STRAP):
                    target = total * k / (N_STRAP - 1.0)
                    while j < len(pts) - 2 and cum[j + 1] < target:
                        j += 1
                    seg = cum[j + 1] - cum[j]
                    t = 0.0 if seg < 1e-12 else (target - cum[j]) / seg
                    a = pts[j]
                    b = pts[j + 1]
                    newp.append((a[0] + (b[0] - a[0]) * t,
                                 a[1] + (b[1] - a[1]) * t,
                                 a[2] + (b[2] - a[2]) * t))
                    a = nrms[j]
                    b = nrms[j + 1]
                    newn.append((a[0] + (b[0] - a[0]) * t,
                                 a[1] + (b[1] - a[1]) * t,
                                 a[2] + (b[2] - a[2]) * t))
                pts = newp
                nrms = newn

            # extend both ends a little below the welt so the band dies into
            # the sole instead of ending with a visible flap on the wall
            ext_len = 0.0042
            if len(pts) > 4:
                p0, p1 = pts[0], pts[1]
                dx, dy, dz = p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2]
                L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                for k in (3, 2, 1):
                    f = ext_len * k / 3.0
                    pts.insert(0, (p0[0] + dx / L * f, p0[1] + dy / L * f, p0[2] + dz / L * f))
                    nrms.insert(0, nrms[0])
                p0, p1 = pts[-1], pts[-2]
                dx, dy, dz = p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2]
                L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                for k in (1, 2, 3):
                    f = ext_len * k / 3.0
                    pts.append((p0[0] + dx / L * f, p0[1] + dy / L * f, p0[2] + dz / L * f))
                    nrms.append(nrms[-1])

            # path tangents (orthogonalise normal against tangent)
            tans = []
            for i in range(len(pts)):
                a = pts[max(0, i - 1)]
                b = pts[min(len(pts) - 1, i + 1)]
                tx = b[0] - a[0]; ty = b[1] - a[1]; tz = b[2] - a[2]
                L = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
                t = (tx / L, ty / L, tz / L)
                n = nrms[i]
                d = n[0] * t[0] + n[1] * t[1] + n[2] * t[2]
                nn = (n[0] - t[0] * d, n[1] - t[1] * d, n[2] - t[2] * d)
                L = math.sqrt(nn[0] ** 2 + nn[1] ** 2 + nn[2] ** 2) or 1.0
                nrms[i] = (nn[0] / L, nn[1] / L, nn[2] / L)
                tans.append(t)

            # band cross-section: a folded penny strap.  b<0 is the toe side,
            # so the folded lip sits on the front edge, behind it the penny
            # bed dips and then a shallow raised keeper rectangle follows.
            hw = strap_w * 0.5
            n0 = -0.00085
            _top = _Curve(
                [0.000, 0.030, 0.070, 0.120, 0.180, 0.215, 0.245, 0.290,
                 0.340, 0.380, 0.500, 0.640, 0.690, 0.725, 0.810, 0.890,
                 0.950, 0.985, 1.000],
                [0.00030, 0.00190, 0.00305, 0.00355, 0.00360, 0.00345,
                 0.00200, 0.00190, 0.00195, 0.00280, 0.00290, 0.00285,
                 0.00270, 0.00195, 0.00180, 0.00160, 0.00100, 0.00050,
                 0.00030],
            )
            nx = [0.0, 0.030, 0.070, 0.120, 0.180, 0.215, 0.245, 0.290,
                  0.340, 0.380, 0.500, 0.640, 0.690, 0.725, 0.810, 0.890,
                  0.950, 0.985, 1.0]
            # CCW: bottom edge (-hw..+hw) then the top edge back (+hw..-hw)
            top_pts = [(-hw + 2.0 * hw * x, _top(x)) for x in nx]
            prof = ([(-hw, n0), (hw, n0)] + list(reversed(top_pts)))

            # fade the band's thickness away where it meets the welt
            cum2 = [0.0]
            for i in range(1, len(pts)):
                cum2.append(cum2[-1] + math.dist(pts[i - 1], pts[i]))
            tot2 = cum2[-1] or 1.0
            uu = [c / tot2 for c in cum2]

            def band_prof(i):
                tp = 0.05 + 0.95 * (_smoothstep(0.0, 0.26, uu[i])
                                    * _smoothstep(1.0, 0.74, uu[i]))
                return [(bb, n0 + (hh - n0) * tp) for (bb, hh) in prof]

            bv, bf = _sweep_profile(pts, nrms, tans, band_prof)
            base = len(uverts)
            uverts.extend(bv)
            ufaces.extend([tuple(i + base for i in f) for f in bf])

    # ---- sole ------------------------------------------------------------
    # ring table: (z fraction, radial offset in m, groove?)
    SOL_RINGS = [
        (0.000, -0.00075, 0),
        (0.045, -0.00040, 0),
        (0.120, -0.00015, 0),
        (0.300, 0.00000, 0),
        (0.362, 0.00000, 0),
        (0.374, 0.00000, 1),
        (0.478, 0.00000, 1),
        (0.490, 0.00000, 0),
        (0.700, 0.00006, 0),
        (0.880, 0.00014, 0),
        (0.958, 0.00018, 0),
        (0.984, 0.00010, 0),
        (1.000, -0.00022, 0),
    ]
    groove_amt = [_smoothstep(0.006, 0.030, SOLE[i][1]) for i in range(N_SOLE)]
    sring = []
    for (zf, off, gr) in SOL_RINGS:
        z = sole_h * zf
        row = []
        for i in range(N_SOLE):
            m = off - (groove_depth * groove_amt[i] if gr else 0.0)
            row.append((SOLE[i][0] + SOLE_N[i][0] * m,
                        SOLE[i][1] + SOLE_N[i][1] * m,
                        z))
        sring.append(row)

    sv = []
    for row in sring:
        sv.extend(row)
    nz = len(sring)
    sf = []
    for k in range(nz - 1):
        for i in range(N_SOLE):
            i1 = (i + 1) % N_SOLE
            a = k * N_SOLE + i
            b = k * N_SOLE + i1
            c = (k + 1) * N_SOLE + i1
            d = (k + 1) * N_SOLE + i
            sf.append((a, b, c, d))
    # bottom cap (fan, normal -Z)
    cx = sum(p[0] for p in SOLE) / N_SOLE
    cy = sum(p[1] for p in SOLE) / N_SOLE
    bot = len(sv)
    sv.append((cx, cy, 0.0))
    for i in range(N_SOLE):
        i1 = (i + 1) % N_SOLE
        sf.append((bot, i1, i))
    # top cap (fan, normal +Z, insole)
    top = len(sv)
    sv.append((cx, cy, sole_h))
    base = (nz - 1) * N_SOLE
    for i in range(N_SOLE):
        i1 = (i + 1) % N_SOLE
        sf.append((top, base + i, base + i1))
    # bottom rim edges -> sharp (crisp sole edge)
    sharp = set()
    for i in range(N_SOLE):
        i1 = (i + 1) % N_SOLE
        sharp.add((min(i, i1), max(i, i1)))

    return {
        "upper": (uverts, ufaces),
        "sole": (sv, sf),
        "sole_sharp": sharp,
    }


# ------------------------------------------------------------ mesh plumbing
def _mesh_bbox(verts):
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def _normal_check(verts, faces, ref_center):
    """True if the face windings point outward."""
    acc = 0.0
    for f in faces[:4000]:
        a = verts[f[0]]
        b = verts[f[1]]
        c = verts[f[2]]
        ux = b[0] - a[0]; uy = b[1] - a[1]; uz = b[2] - a[2]
        vx = c[0] - a[0]; vy = c[1] - a[1]; vz = c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        px = (a[0] + b[0] + c[0]) / 3.0 - ref_center[0]
        py = (a[1] + b[1] + c[1]) / 3.0 - ref_center[1]
        pz = (a[2] + b[2] + c[2]) / 3.0 - ref_center[2]
        acc += nx * px + ny * py + nz * pz
    return acc > 0.0


def _flip(faces):
    return [tuple(reversed(f)) for f in faces]


def _make_object(name, verts, faces, sharp_edges=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(verbose=False)
    me.update()
    if len(me.polygons):
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if sharp_edges:
        for e in me.edges:
            a = e.vertices[0]
            b = e.vertices[1]
            if (min(a, b), max(a, b)) in sharp_edges:
                e.use_edge_sharp = True
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ------------------------------------------------------------------ public
def build_loafer(name="loafer", side="R",
                 length=0.155, width=0.070, height=0.080,
                 sole_h=0.0105, toe_rise=0.030,
                 strap=True, strap_w=0.013, strap_y=-0.020,
                 toe_round=1.0, origin=(0.0, 0.0, 0.0)):
    """Build a chibi penny loafer.

    Parameters
    ----------
    name    : object name for the upper (the sole gets ``name + "_sole"``)
    side    : "R" (character's right, lateral side at x<0) or "L" (mirrored)
    length  : overall sole length (m), toe tip at y = -0.677*length
    width   : overall width (m)
    height  : top of the collar rim (m)
    sole_h  : sole thickness (m)
    toe_rise: height of the toe-box crest above the sole top (m)
    strap   : build the penny strap + keeper
    strap_w : strap width across the vamp (m)
    strap_y : requested strap centre in y (clamped so it stays on the vamp)
    toe_round : >1 chubbier / higher toe box, <1 flatter
    origin  : world offset added to every vertex

    Returns
    -------
    (upper, sole) : bpy.types.Object, vertices already in world space,
                    identity object transform, smooth shaded, no material.
    """
    geo = _build_core(length, width, height, sole_h, toe_rise,
                      strap, strap_w, strap_y, toe_round)

    up_v, up_f = geo["upper"]
    so_v, so_f = geo["sole"]

    # outward check (per shell; the upper is open so use a radial reference)
    ref = (0.0, 0.005, 0.5 * (sole_h + height))
    if not _normal_check(up_v, up_f, ref):
        up_f = _flip(up_f)
    if not _normal_check(so_v, so_f, ref):
        so_f = _flip(so_f)

    mirror = str(side).upper().startswith("L")
    ox, oy, oz = origin

    def place(vs):
        if mirror:
            return [(-(v[0]) + ox, v[1] + oy, v[2] + oz) for v in vs]
        return [(v[0] + ox, v[1] + oy, v[2] + oz) for v in vs]

    up_v = place(up_v)
    so_v = place(so_v)
    if mirror:
        up_f = _flip(up_f)
        so_f = _flip(so_f)

    sharp = geo["sole_sharp"]

    upper = _make_object(name, up_v, up_f)
    sole = _make_object(name + "_sole", so_v, so_f, sharp_edges=sharp)
    return upper, sole
