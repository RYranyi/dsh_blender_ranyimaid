"""
hand.py -- procedural chibi hand for Blender 5.x

A single self-contained module.  Everything is generated from an implicit
signed-distance field (palm blobs + tapered finger capsule chains + thumb),
polygonised with a vectorised surface-nets mesher and relaxed with a Taubin
(lambda/mu) smoother.  Result: one closed, organic, smooth-shaded mesh.

Local frame (meters, matching the character scale contract):
    * wrist cross-section centred on the origin,
    * hand grows along +Z (wrist z=0 -> fingertip z~0.070),
    * palm normal points to -Y  (camera at -Y sees the palm),
    * side="R" puts the thumb on the +X side; "L" is the X mirror.

Public API
----------
build_hand(name="hand", side="R", length=0.070, palm_w=0.052, palm_t=0.026,
           curl=0.30, spread=0.06, thumb_grip=0.35, smooth_fingers=True)
    -> bpy.types.Object   (mesh data in local coords, smooth shaded, no material)

No external assets, no randomness: the same arguments always produce the same
mesh.
"""

from __future__ import annotations

import math
import time

import numpy as np
import bpy

# --------------------------------------------------------------------------
# tuning constants (design space, metres)
# --------------------------------------------------------------------------
DESIGN_LEN = 0.0700          # wrist->fingertip of the nominal design
DESIGN_PALM_W = 0.0520
DESIGN_PALM_T = 0.0260

VOXEL = 0.00075              # implicit-surface voxel size (<= 0.0008)
TAUBIN_ITERS = 24            # smoothing passes when smooth_fingers=True
TAUBIN_LAMBDA = 0.52
TAUBIN_MU = -0.55

# grid bounds of the design (a little padding around the hand)
GRID_LO = np.array((-0.0375, -0.0305, -0.0030))
GRID_HI = np.array((0.0375, 0.0185, 0.0745))

# finger table:  x, z_base, path-length, r_base, r_tip, splay-multiplier, curl-mult
_FINGERS = (
    ("index",  +0.01900, 0.0326, 0.0292, 0.00662, 0.00585, +1.90, 1.00),
    ("middle", +0.00630, 0.0342, 0.0314, 0.00685, 0.00608, +0.50, 1.02),
    ("ring",   -0.00630, 0.0330, 0.0304, 0.00655, 0.00582, -0.50, 1.06),
    ("pinky",  -0.01900, 0.0292, 0.0246, 0.00575, 0.00515, -2.00, 1.10),
)

# thumb path (R hand), radii
_THUMB_PTS = (
    (0.0212, -0.0022, 0.0130),
    (0.0249, -0.0092, 0.0246),
    (0.0228, -0.0152, 0.0338),
    (0.0178, -0.0179, 0.0426),
    (0.0132, -0.0172, 0.0486),
)
_THUMB_R = (0.00750, 0.00735, 0.00665, 0.00610, 0.00545)

# radius profile along a finger (t, multiplier of r_base)
_RAD_T = (0.00, 0.14, 0.30, 0.44, 0.56, 0.70, 0.82, 0.92, 1.00)
_RAD_V = (1.00, 0.975, 0.995, 0.960, 0.940, 0.965, 0.915, 0.890, 0.885)

# palm loft: z control points, half-width, half-thickness, y-centre offset
_PALM_Z = (-0.0080, 0.0000, 0.0060, 0.0120, 0.0180, 0.0240,
           0.0285, 0.0315, 0.0345, 0.0370, 0.0390, 0.0402)
_PALM_A = (0.0192, 0.0206, 0.0212, 0.0221, 0.0232, 0.0243,
           0.0251, 0.0256, 0.0257, 0.0249, 0.0222, 0.0150)
_PALM_B = (0.0106, 0.0115, 0.0118, 0.0120, 0.0121, 0.0122,
           0.0123, 0.0122, 0.0119, 0.0111, 0.0096, 0.0070)
_PALM_C = (0.0000, 0.0000, 0.0002, 0.0006, 0.0010, 0.0012,
           0.0012, 0.0011, 0.0009, 0.0007, 0.0006, 0.0005)


# --------------------------------------------------------------------------
# tiny vector helpers
# --------------------------------------------------------------------------
def _norm(v):
    v = np.asarray(v, dtype=np.float64)
    n = math.sqrt(float(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))
    return v / (n if n > 1e-15 else 1.0)


def _rot(v, axis, ang):
    """Rodrigues rotation of v about unit `axis` by `ang` radians."""
    c, s = math.cos(ang), math.sin(ang)
    ax = np.cross(axis, v)
    d = float(np.dot(axis, v))
    return v * c + ax * s + axis * (d * (1.0 - c))


def _spline(t, xs, ys):
    """Cubic Hermite (Catmull-Rom tangents) interpolation, clamped."""
    if t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    i = 0
    while i < len(xs) - 2 and t > xs[i + 1]:
        i += 1
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    h = x1 - x0
    m0 = 0.0 if i == 0 else (ys[i + 1] - ys[i - 1]) / (xs[i + 1] - xs[i - 1])
    m1 = 0.0 if i + 2 >= len(xs) else (ys[i + 2] - ys[i]) / (xs[i + 2] - xs[i])
    u = (t - x0) / h
    u2 = u * u
    u3 = u2 * u
    return ((2 * u3 - 3 * u2 + 1) * y0 + (u3 - 2 * u2 + u) * h * m0
            + (-2 * u3 + 3 * u2) * y1 + (u3 - u2) * h * m1)


# --------------------------------------------------------------------------
# SDF primitives -- all take broadcastable (X, Y, Z) arrays
# --------------------------------------------------------------------------
def _sd_sphere(X, Y, Z, c, r):
    dx = X - c[0]
    dy = Y - c[1]
    dz = Z - c[2]
    return np.sqrt(dx * dx + dy * dy + dz * dz) - r


def _sd_ellipsoid(X, Y, Z, c, r):
    dx = (X - c[0]) / r[0]
    dy = (Y - c[1]) / r[1]
    dz = (Z - c[2]) / r[2]
    k0 = np.sqrt(dx * dx + dy * dy + dz * dz)
    k1 = np.sqrt((dx / r[0]) ** 2 + (dy / r[1]) ** 2 + (dz / r[2]) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def _sd_ellipsoid_rot(X, Y, Z, c, axes, cols):
    """Ellipsoid with an arbitrary orientation. cols = (u, v, w) local axes."""
    dx = X - c[0]
    dy = Y - c[1]
    dz = Z - c[2]
    u, v, w = cols
    lx = dx * u[0] + dy * u[1] + dz * u[2]
    ly = dx * v[0] + dy * v[1] + dz * v[2]
    lz = dx * w[0] + dy * w[1] + dz * w[2]
    ax, ay, az = axes
    k0 = np.sqrt((lx / ax) ** 2 + (ly / ay) ** 2 + (lz / az) ** 2)
    k1 = np.sqrt((lx / (ax * ax)) ** 2 + (ly / (ay * ay)) ** 2 + (lz / (az * az)) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def _sd_round_box(X, Y, Z, c, half, r):
    qx = np.abs(X - c[0]) - (half[0] - r)
    qy = np.abs(Y - c[1]) - (half[1] - r)
    qz = np.abs(Z - c[2]) - (half[2] - r)
    ax = np.maximum(qx, 0.0)
    ay = np.maximum(qy, 0.0)
    az = np.maximum(qz, 0.0)
    outside = np.sqrt(ax * ax + ay * ay + az * az)
    inside = np.minimum(np.maximum(np.maximum(qx, qy), qz), 0.0)
    return outside + inside - r


def _sd_round_cone(X, Y, Z, a, b, r1, r2):
    """Exact round cone (capsule with linearly varying radius)."""
    bax = b[0] - a[0]
    bay = b[1] - a[1]
    baz = b[2] - a[2]
    l2 = bax * bax + bay * bay + baz * baz
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pax = X - a[0]
    pay = Y - a[1]
    paz = Z - a[2]
    y = pax * bax + pay * bay + paz * baz
    z = y - l2
    xx = pax * l2 - bax * y
    yy = pay * l2 - bay * y
    zz = paz * l2 - baz * y
    x2 = xx * xx + yy * yy + zz * zz
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    r_cap2 = np.sqrt(x2 + z2) * il2 - r2
    r_cap1 = np.sqrt(x2 + y2) * il2 - r1
    r_side = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, r_cap2,
                    np.where(np.sign(y) * a2 * y2 < k, r_cap1, r_side))


def _sd_loft(X, Y, Z, a, b, yc, zc, rz, rnd, k_cap=0.0035):
    """Lofted superellipse-ish volume: z-varying rounded-rect cross-section
    (centre offset yc, dorsal/palmar asymmetry comes from yc), softly capped."""
    qx = np.abs(X) - (a - rnd)
    qy = np.abs(Y - yc) - (b - rnd)
    ax = np.maximum(qx, 0.0)
    ay = np.maximum(qy, 0.0)
    lateral = np.sqrt(ax * ax + ay * ay) + np.minimum(np.maximum(qx, qy), 0.0) - rnd
    dz = np.abs(Z - zc) - rz
    return _smax(lateral, dz, k_cap)


def _smin(a, b, k):
    """Quadratic smooth minimum (fillet radius ~ k/4)."""
    if k <= 0.0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def _smax(a, b, k):
    return -_smin(-a, -b, k)


# --------------------------------------------------------------------------
# scalar field on a regular grid, with sub-box blend operations
# --------------------------------------------------------------------------
class _Field:
    def __init__(self, lo, hi, h, fill=0.5):
        self.h = float(h)
        self.lo = np.asarray(lo, dtype=np.float64)
        n = np.ceil((np.asarray(hi, float) - self.lo) / h).astype(int) + 1
        self.n = tuple(int(v) for v in n)
        self.arr = np.full(self.n, float(fill), dtype=np.float32)
        self.xs = self.lo[0] + np.arange(self.n[0]) * h
        self.ys = self.lo[1] + np.arange(self.n[1]) * h
        self.zs = self.lo[2] + np.arange(self.n[2]) * h

    # ---- helpers ---------------------------------------------------------
    def _idx(self, slab):
        (x0, x1), (y0, y1), (z0, z1) = slab
        i0 = max(0, int(math.floor((x0 - self.lo[0]) / self.h)))
        i1 = min(self.n[0], int(math.ceil((x1 - self.lo[0]) / self.h)) + 1)
        j0 = max(0, int(math.floor((y0 - self.lo[1]) / self.h)))
        j1 = min(self.n[1], int(math.ceil((y1 - self.lo[1]) / self.h)) + 1)
        k0 = max(0, int(math.floor((z0 - self.lo[2]) / self.h)))
        k1 = min(self.n[2], int(math.ceil((z1 - self.lo[2]) / self.h)) + 1)
        return i0, i1, j0, j1, k0, k1

    def _coords(self, i0, i1, j0, j1, k0, k1):
        X = self.xs[i0:i1].reshape((-1, 1, 1)).astype(np.float32)
        Y = self.ys[j0:j1].reshape((1, -1, 1)).astype(np.float32)
        Z = self.zs[k0:k1].reshape((1, 1, -1)).astype(np.float32)
        return X, Y, Z

    def blend(self, fn, slab, k=0.0, op="union", pad=0.0):
        """fn(X,Y,Z)->d  applied inside `slab` (world bbox), blended into arr."""
        slab = [(slab[0][0] - pad, slab[0][1] + pad),
                (slab[1][0] - pad, slab[1][1] + pad),
                (slab[2][0] - pad, slab[2][1] + pad)]
        i0, i1, j0, j1, k0, k1 = self._idx(slab)
        if i0 >= i1 or j0 >= j1 or k0 >= k1:
            return
        X, Y, Z = self._coords(i0, i1, j0, j1, k0, k1)
        d = fn(X, Y, Z)
        sub = self.arr[i0:i1, j0:j1, k0:k1]
        if op == "union":
            self.arr[i0:i1, j0:j1, k0:k1] = _smin(sub, d, k)
        else:
            self.arr[i0:i1, j0:j1, k0:k1] = _smax(sub, -d, k)

    def blend_field(self, other, k, slab=None):
        if slab is None:
            self.arr = _smin(self.arr, other.arr, k)
            return
        i0, i1, j0, j1, k0, k1 = self._idx(slab)
        self.arr[i0:i1, j0:j1, k0:k1] = _smin(
            self.arr[i0:i1, j0:j1, k0:k1], other.arr[i0:i1, j0:j1, k0:k1], k)

    def cut_plane_z(self, z0, k):
        """smax(field, -(z - z0)) for the slab near and below z0."""
        j = int(min(self.n[2], math.ceil((z0 + 6.0 * k - self.lo[2]) / self.h) + 2))
        Z = self.zs[:j].reshape((1, 1, -1)).astype(np.float32)
        sub = self.arr[:, :, :j]
        self.arr[:, :, :j] = _smax(sub, -(Z - z0), k)


# --------------------------------------------------------------------------
# surface nets polygoniser  (vectorised)
# --------------------------------------------------------------------------
def _surface_nets(field, h, lo):
    s = field
    nx, ny, nz = s.shape

    cs = {}
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                cs[(di, dj, dk)] = s[di:nx - 1 + di, dj:ny - 1 + dj, dk:nz - 1 + dk]

    order = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
             (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
    vmin = np.minimum.reduce([cs[c] for c in order])
    vmax = np.maximum.reduce([cs[c] for c in order])
    active = (vmin < 0.0) & (vmax >= 0.0)
    idx = np.nonzero(active)
    m = idx[0].size
    if m == 0:
        return np.zeros((0, 3)), np.zeros((0, 4), np.int32)

    v = np.empty((m, 8), np.float32)
    for ci, c in enumerate(order):
        v[:, ci] = cs[c][idx]

    # 12 cell edges, corners indexed by (di*4 + dj*2 + dk)
    def cid_of(di, dj, dk):
        return di * 4 + dj * 2 + dk

    edges = []
    for a in range(8):
        ai, aj, ak = (a >> 2) & 1, (a >> 1) & 1, a & 1
        for b in range(a + 1, 8):
            bi, bj, bk = (b >> 2) & 1, (b >> 1) & 1, b & 1
            if abs(ai - bi) + abs(aj - bj) + abs(ak - bk) == 1:
                edges.append((a, b))

    acc = np.zeros((m, 3), np.float64)
    cnt = np.zeros(m, np.float64)
    for a, b in edges:
        va = v[:, a]
        vb = v[:, b]
        cross = (va < 0.0) != (vb < 0.0)
        den = va - vb
        den = np.where(np.abs(den) < 1e-20, 1e-20, den)
        t = va / den
        pa = np.array([(a >> 2) & 1, (a >> 1) & 1, a & 1], np.float64)
        pb = np.array([(b >> 2) & 1, (b >> 1) & 1, b & 1], np.float64)
        for d in range(3):
            acc[:, d] += np.where(cross, pa[d] + t * (pb[d] - pa[d]), 0.0)
        cnt += cross
    bad = cnt < 0.5
    cnt[bad] = 1.0
    vcell = acc / cnt[:, None]

    verts = np.stack(idx, axis=1).astype(np.float64) + vcell
    verts = lo[None, :] + verts * h

    cid = np.full(((nx - 1), (ny - 1), (nz - 1)), -1, np.int64)
    cid[idx] = np.arange(m)

    quads = []

    # ---- x edges
    e = (s[1:, :, :] < 0.0) != (s[:-1, :, :] < 0.0)
    e = e[:, 1:ny - 1, 1:nz - 1]
    ii, jj, kk = np.nonzero(e)
    jj = jj + 1
    kk = kk + 1
    if ii.size:
        ins = s[ii, jj, kk] < 0.0
        q = np.stack([cid[ii, jj - 1, kk - 1], cid[ii, jj, kk - 1],
                      cid[ii, jj, kk], cid[ii, jj - 1, kk]], axis=1)
        ok = np.all(q >= 0, axis=1)
        q = q[ok]
        ins = ins[ok]
        qf = q.copy()
        qf[~ins] = q[~ins][:, ::-1]
        quads.append(qf)

    # ---- y edges  (+y order: (i-1,k-1),(i-1,k),(i,k),(i,k-1))
    e = (s[:, 1:, :] < 0.0) != (s[:, :-1, :] < 0.0)
    e = e[1:nx - 1, :, 1:nz - 1]
    ii, jj, kk = np.nonzero(e)
    ii = ii + 1
    kk = kk + 1
    if ii.size:
        ins = s[ii, jj, kk] < 0.0
        q = np.stack([cid[ii - 1, jj, kk - 1], cid[ii - 1, jj, kk],
                      cid[ii, jj, kk], cid[ii, jj, kk - 1]], axis=1)
        ok = np.all(q >= 0, axis=1)
        q = q[ok]
        ins = ins[ok]
        qf = q.copy()
        qf[~ins] = q[~ins][:, ::-1]
        quads.append(qf)

    # ---- z edges  (+z order: (i-1,j-1),(i,j-1),(i,j),(i-1,j))
    e = (s[:, :, 1:] < 0.0) != (s[:, :, :-1] < 0.0)
    e = e[1:nx - 1, 1:ny - 1, :]
    ii, jj, kk = np.nonzero(e)
    ii = ii + 1
    jj = jj + 1
    if ii.size:
        ins = s[ii, jj, kk] < 0.0
        q = np.stack([cid[ii - 1, jj - 1, kk], cid[ii, jj - 1, kk],
                      cid[ii, jj, kk], cid[ii - 1, jj, kk]], axis=1)
        ok = np.all(q >= 0, axis=1)
        q = q[ok]
        ins = ins[ok]
        qf = q.copy()
        qf[~ins] = q[~ins][:, ::-1]
        quads.append(qf)

    faces = np.concatenate(quads, axis=0) if quads else np.zeros((0, 4), np.int64)
    return verts, faces


def _sample_field(field, lo, h, pts):
    """Trilinear sample of the SDF grid at world points (n,3)."""
    q = (pts - lo) / h
    i = np.floor(q).astype(np.int64)
    f = q - i
    n = np.array(field.shape)
    i = np.clip(i, 0, n - 2)
    x0, y0, z0 = i[:, 0], i[:, 1], i[:, 2]
    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    out = np.zeros(pts.shape[0], np.float64)
    for dx in (0, 1):
        wx = fx if dx else 1.0 - fx
        for dy in (0, 1):
            wy = fy if dy else 1.0 - fy
            for dz in (0, 1):
                wz = fz if dz else 1.0 - fz
                out += wx * wy * wz * field[x0 + dx, y0 + dy, z0 + dz]
    return out


def _project_to_surface(field, lo, h, v, iters=3, max_step=0.0005):
    """Newton-project vertices onto the SDF zero set (kills surface-nets bias)."""
    v = v.astype(np.float64).copy()
    eps = h
    off = np.array([[eps, 0, 0], [0, eps, 0], [0, 0, eps]], np.float64)
    for _ in range(iters):
        d = _sample_field(field, lo, h, v)
        g = np.empty((v.shape[0], 3), np.float64)
        for k in range(3):
            gp = _sample_field(field, lo, h, v + off[k])
            gm = _sample_field(field, lo, h, v - off[k])
            g[:, k] = (gp - gm) / (2.0 * eps)
        g2 = np.maximum((g * g).sum(1), 1e-8)
        step = (-d[:, None] * g) / g2[:, None]
        ln = np.sqrt((step * step).sum(1))
        scl = np.minimum(1.0, max_step / np.maximum(ln, 1e-12))
        v += step * scl[:, None]
    return v


# --------------------------------------------------------------------------
# Taubin smoothing (volume preserving-ish lambda/mu smoothing)
# --------------------------------------------------------------------------
def _neighbours(verts, faces):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]],
                        faces[:, [2, 3]], faces[:, [3, 0]]], axis=0)
    e = np.concatenate([e, e[:, ::-1]], axis=0)
    a = e[:, 0]
    b = e[:, 1]
    n = verts.shape[0]
    cnt = np.bincount(a, minlength=n).astype(np.float64)
    cnt[cnt == 0] = 1.0
    return a, b, cnt


def _taubin(verts, faces, iters, lam=0.52, mu=-0.55, pin=None):
    a, b, cnt = _neighbours(verts, faces)
    n = verts.shape[0]
    v = verts.astype(np.float64).copy()
    free = np.ones(n, np.float64)
    if pin is not None:
        free[pin] = 0.0
    free = free[:, None]
    for it in range(iters):
        f = lam if (it % 2 == 0) else mu
        acc = np.empty((n, 3), np.float64)
        for d in range(3):
            acc[:, d] = np.bincount(a, weights=v[b, d], minlength=n)
        avg = acc / cnt[:, None]
        v += f * (avg - v) * free
    return v


# --------------------------------------------------------------------------
# hand construction
# --------------------------------------------------------------------------
def _finger_chain(base, length, r_base, r_tip, spread_rad, curl_total, curl_mult,
                  nseg=16):
    """Return (points+radii, tangents, binormals, dorsals) for a curled finger."""
    T = _norm(np.array([math.sin(spread_rad), 0.0, math.cos(spread_rad)]))
    N = np.array([0.0, -1.0, 0.0])
    B = _norm(np.cross(T, N))

    ts = np.linspace(0.0, 1.0, nseg + 1)
    # bend concentrated at the MCP (base), then PIP, then DIP -- relaxed hand
    w = (0.42 * np.exp(-((ts - 0.06) / 0.17) ** 2)
         + 0.36 * np.exp(-((ts - 0.50) / 0.23) ** 2)
         + 0.22 * np.exp(-((ts - 0.86) / 0.17) ** 2))
    w = w / w.sum()

    p = np.asarray(base, np.float64).copy()
    ds = length / nseg
    pts = [(p.copy(), _spline(0.0, _RAD_T, _RAD_V) * r_base)]
    dirs = [T.copy()]
    bs = [B.copy()]
    for i in range(nseg):
        p = p + T * ds
        T = _norm(_rot(T, B, curl_total * curl_mult * w[i + 1]))
        t = ts[i + 1]
        rr = _spline(t, _RAD_T, _RAD_V) * r_base
        if t > 0.9:
            rr = rr * (1.0 - (t - 0.9) / 0.1) + r_tip * ((t - 0.9) / 0.1)
        pts.append((p.copy(), rr))
        dirs.append(T.copy())
        bs.append(_norm(np.cross(T, N)))
    pts[-1] = (pts[-1][0], r_tip)
    Bs = [np.array(b) for b in bs]
    Ns = [_norm(np.cross(dirs[i], bs[i])) for i in range(len(bs))]
    return pts, dirs, Bs, Ns


def _chain_sdf(pts):
    """Union of round cones along the chain."""
    def fn(X, Y, Z):
        d = None
        for i in range(len(pts) - 1):
            a, r1 = pts[i]
            b, r2 = pts[i + 1]
            dd = _sd_round_cone(X, Y, Z, a, b, r1, r2)
            d = dd if d is None else np.minimum(d, dd)
        return d
    return fn


def _chain_bbox(pts, pad=0.0015):
    p = np.array([q[0] for q in pts])
    r = max(q[1] for q in pts) + pad
    return [(p[:, 0].min() - r, p[:, 0].max() + r),
            (p[:, 1].min() - r, p[:, 1].max() + r),
            (p[:, 2].min() - r, p[:, 2].max() + r)]


def _build_field(curl, spread, thumb_grip, smooth_fingers):
    h = VOXEL
    palm = _Field(GRID_LO, GRID_HI, h)
    digits = _Field(GRID_LO, GRID_HI, h)

    k_soft = 0.0065 if smooth_fingers else 0.0045

    # ---------------- palm mass ----------------
    # Lofted palm: smooth z-varying rounded-rectangle cross section.  A single
    # primitive, so the silhouette is exactly the profile table (no smin bulge).
    pz = _PALM_Z
    tab_z = np.linspace(pz[0], pz[-1], 321)
    tab_a = np.array([_spline(z, pz, _PALM_A) for z in tab_z])
    tab_b = np.array([_spline(z, pz, _PALM_B) for z in tab_z])
    tab_c = np.array([_spline(z, pz, _PALM_C) for z in tab_z])
    lo_z = pz[0]
    hi_z = pz[-1]
    zc = 0.5 * (lo_z + hi_z)
    rz = 0.5 * (hi_z - lo_z)

    def palm_sdf(X, Y, Z):
        a = np.interp(Z, tab_z, tab_a).astype(np.float32)
        b = np.interp(Z, tab_z, tab_b).astype(np.float32)
        c = np.interp(Z, tab_z, tab_c).astype(np.float32)
        rnd = np.minimum(np.minimum(a, b) * 0.42, 0.0060)
        return _sd_loft(X, Y, Z, a, b, c, zc, rz, rnd, k_cap=0.0040)

    palm.blend(palm_sdf, [(-0.033, 0.033), (-0.03, 0.03), (lo_z, hi_z)],
               0.0, pad=0.006)
    palm.cut_plane_z(-0.0020, 0.00040)

    # thenar (thumb-side) pad
    palm.blend(lambda X, Y, Z: _sd_ellipsoid(
        X, Y, Z, (0.0135, -0.0042, 0.0188), (0.0102, 0.0094, 0.0128)),
        [(-0.005, 0.03), (-0.03, 0.01), (0.0, 0.034)], 0.0085, pad=0.012)

    # hypothenar (pinky-side) pad
    palm.blend(lambda X, Y, Z: _sd_ellipsoid(
        X, Y, Z, (-0.0138, -0.0034, 0.0196), (0.0090, 0.0088, 0.0118)),
        [(-0.03, 0.005), (-0.03, 0.01), (0.0, 0.034)], 0.0075, pad=0.012)

    # knuckle bumps on the back of the hand
    for name, x, zbase, ln, rb, rt, spl, cm in _FINGERS:
        kx = x * 0.985
        kz = zbase + 0.0018
        palm.blend(lambda X, Y, Z, c=(kx, 0.0096, kz):
                   _sd_ellipsoid(X, Y, Z, c, (0.0050, 0.0032, 0.0040)),
                   [(kx - 0.009, kx + 0.009), (0.005, 0.017), (kz - 0.008, kz + 0.008)],
                   0.0065, pad=0.008)

    # shallow palm cup (helps the thumb read as "resting on" the palm)
    # -- the palmar arch is built into the loft (yc profile); nothing to add here

    # ---------------- digits ----------------
    k_dig = 0.0028 if smooth_fingers else 0.0020
    for name, x, zbase, ln, rb, rt, spl, cm in _FINGERS:
        pts, dirs, Bs, Ns = _finger_chain(
            (x, 0.0022, zbase), ln, rb, rt, spread * spl,
            math.radians(145.0) * curl, cm)
        bbox = _chain_bbox(pts)
        digits.blend(_chain_sdf(pts), bbox, k_dig, pad=0.006)
        # plump, slightly flattened fingertip pad
        pe = pts[-1][0] + dirs[-1] * (0.18 * rt)
        axes = (0.90 * rt, 1.06 * rt, 1.02 * rt)
        cols = (dirs[-1], Bs[-1], Ns[-1])
        pad_bb = [(pe[i] - 1.2 * rt, pe[i] + 1.2 * rt) for i in range(3)]
        digits.blend(lambda X, Y, Z, c=pe, a=axes, cl=cols:
                     _sd_ellipsoid_rot(X, Y, Z, c, a, cl),
                     pad_bb, k_dig, pad=0.004)
        # nail-bed hint: a very shallow flattening of the dorsal distal surface
        i_n = max(2, int(round(0.78 * (len(pts) - 1))))
        pn = pts[i_n][0]
        rn = pts[i_n][1]
        dn = _norm(np.cross(dirs[i_n], Bs[i_n]))     # dorsal
        cn = pn + dn * (rn * 1.56 - 0.00026)
        nail_axes = (0.54 * rn, 0.58 * rn, 0.50 * rn)
        nbb = [(cn[i] - 1.0 * rn, cn[i] + 1.0 * rn) for i in range(3)]
        digits.blend(lambda X, Y, Z, c=cn, a=nail_axes, cl=(dirs[i_n], Bs[i_n], dn):
                     _sd_ellipsoid_rot(X, Y, Z, c, a, cl),
                     nbb, 0.0012, op="sub", pad=0.004)

    # ---------------- thumb ----------------
    g = (thumb_grip - 0.35)
    shift3 = np.array([0.0060, 0.0050, 0.0030]) * g / 0.65
    shift4 = np.array([0.0075, 0.0060, 0.0038]) * g / 0.65
    tp = [np.array(p, float) for p in _THUMB_PTS]
    tp[3] = tp[3] + shift3
    tp[4] = tp[4] + shift4
    tpts = [(tp[i], _THUMB_R[i]) for i in range(5)]
    # densify for a smooth sweep
    tden = []
    for i in range(4):
        for s in range(3):
            u = s / 3.0
            p = tpts[i][0] * (1 - u) + tpts[i + 1][0] * u
            r = tpts[i][1] * (1 - u) + tpts[i + 1][1] * u
            tden.append((p, r))
    tden.append(tpts[-1])
    digits.blend(_chain_sdf(tden), _chain_bbox(tden), k_dig, pad=0.006)
    # thumb tip pad
    Tt = _norm(tden[-1][0] - tden[-2][0])
    Bt2 = _norm(np.cross(Tt, np.array([0.0, -1.0, 0.0])))
    Nt2 = _norm(np.cross(Bt2, Tt))
    rt_t = tden[-1][1]
    pc = tden[-1][0] + Tt * (0.16 * rt_t)
    digits.blend(lambda X, Y, Z: _sd_ellipsoid_rot(
        X, Y, Z, pc, (0.90 * rt_t, 1.06 * rt_t, 1.02 * rt_t), (Tt, Bt2, Nt2)),
        [(pc[i] - 1.2 * rt_t, pc[i] + 1.2 * rt_t) for i in range(3)],
        k_dig, pad=0.004)

    # ---------------- merge ----------------
    palm.blend_field(digits, k_web(curl, smooth_fingers))
    return palm


def k_web(curl, smooth_fingers):
    base = 0.0086 if smooth_fingers else 0.0062
    return base * (0.80 + 0.20 * min(1.0, max(0.0, curl / 0.45)))


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def build_hand(name="hand", side="R", length=0.070, palm_w=0.052, palm_t=0.026,
               curl=0.30, spread=0.06, thumb_grip=0.35, smooth_fingers=True):
    """Build a chibi hand and return it as a single joined, smooth-shaded object.

    Parameters
    ----------
    name            object / mesh name
    side            "R" = character's right hand (thumb on +X), "L" mirrored
    length          wrist -> fingertip length (m)
    palm_w          palm width across the knuckles (m)
    palm_t          palm thickness (m)
    curl            0 = straight fingers, 1 = relaxed fist
    spread          finger splay (radians; scales a per-finger splay profile)
    thumb_grip      how far the thumb wraps toward the index (0..1, 0.35 rest)
    smooth_fingers  stronger implicit blending + more surface relaxation
    """
    t0 = time.time()
    side = str(side).upper()
    curl = float(min(1.0, max(0.0, curl)))
    spread = float(spread)
    smooth_fingers = bool(smooth_fingers)

    field = _build_field(curl, spread, float(thumb_grip), smooth_fingers)
    verts, faces = _surface_nets(field.arr, field.h, field.lo)

    # ---- relax + project back onto the exact iso-surface ------------------
    iters = TAUBIN_ITERS if smooth_fingers else 8
    verts = _taubin(verts, faces, iters, TAUBIN_LAMBDA, TAUBIN_MU)
    verts = _project_to_surface(field.arr, field.lo, field.h, verts,
                                iters=3, max_step=0.0006)

    # ---- anisotropic size mapping (length / palm width / thickness) -------
    sx = float(palm_w) / DESIGN_PALM_W
    sy = float(palm_t) / DESIGN_PALM_T
    sz = float(length) / DESIGN_LEN
    verts[:, 0] *= sx
    verts[:, 1] *= sy
    verts[:, 2] *= sz

    if side == "L":
        verts[:, 0] *= -1.0
        faces = faces[:, ::-1]

    # ---- mesh ------------------------------------------------------------
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], faces.tolist())
    me.validate(verbose=False, clean_customdata=False)
    me.update()

    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)

    # ---- weld, cut the wrist flat at z=0, cap it, clean normals ----------
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)

    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    res = bmesh.ops.bisect_plane(
        bm, geom=geom, dist=1e-9,
        plane_co=(0.0, 0.0, 0.0), plane_no=(0.0, 0.0, 1.0),
        clear_inner=True, clear_outer=False)
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if cut_edges:
        bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)

    # snap the cut ring exactly onto z=0
    for v in bm.verts:
        if abs(v.co.z) < 1e-7:
            v.co.z = 0.0

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # the wrist cap is the biggest face; keep its rim shading crisp
    cap = max(bm.faces, key=lambda f: len(f.verts)) if bm.faces else None
    if cap is not None and len(cap.verts) > 6:
        for e in cap.edges:
            e.smooth = False

    bm.to_mesh(me)
    bm.free()
    me.update()

    for p in me.polygons:
        p.use_smooth = True
    ob.data.update()

    ob.location = (0.0, 0.0, 0.0)
    ob["hand_build_seconds"] = round(time.time() - t0, 3)
    return ob


# --------------------------------------------------------------------------
if __name__ == "__main__":
    for s in ("R", "L"):
        o = build_hand(name="hand_" + s, side=s)
        vs = o.data.vertices
        xs = [v.co.x for v in vs]
        ys = [v.co.y for v in vs]
        zs = [v.co.z for v in vs]
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        print("HAND", s, "verts", len(vs), "faces", len(o.data.polygons),
              "tris", tris,
              "bbox", [round(min(xs), 5), round(max(xs), 5),
                       round(min(ys), 5), round(max(ys), 5),
                       round(min(zs), 5), round(max(zs), 5)],
              "t", o["hand_build_seconds"])
