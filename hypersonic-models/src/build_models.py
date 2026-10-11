"""
Parametric display models of hypersonic vehicles for FDM printing (PLA/PLA+).

Run:  python build_models.py        (needs: pip install cadquery)
Outputs STL (for slicing) and STEP (for editing in Fusion / SolidWorks) into
../stl and ../step.  Every dimension below is in full-scale METRES and is
converted to model millimetres with the vehicle's scale factor, so changing
SCALE re-sizes the geometry while keeping the fit features (pins, slots,
sockets) at fixed printable sizes.

Outer mold lines are APPROXIMATIONS from public dimensions and photographs.
They are display / teaching models, not wind-tunnel-accurate geometry.
"""

import math
import os

import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, ".."))
STL_DIR = os.path.join(OUT, "stl")
STEP_DIR = os.path.join(OUT, "step")

# ---- fit features (model mm, independent of scale) -------------------------
CLEAR = 0.20          # per-side clearance for tabs in slots
PIN_D = 1.95          # alignment pin holes: use 1.75 mm filament as pins
PIN_DEPTH = 3.5       # hole depth in EACH half -> cut pins to 2*depth - 0.5
SOCKET_D = 6.3        # stand socket (stand peg is 6.0 mm)
SOCKET_DEPTH = 6.5
PEG_D = 6.0
PEG_LEN = 6.0
POST_D = 8.0

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def superellipse_wire(x, a, zc, ht, hb, nt=2.0, nb=2.0, n=32):
    """Closed spline cross-section in the plane X=x.
    a = half width, ht/hb = top/bottom half heights, nt/nb = exponents."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        e, h = (nt, ht) if s >= 0 else (nb, hb)
        y = a * math.copysign(abs(c) ** (2.0 / e), c)
        z = zc + h * math.copysign(abs(s) ** (2.0 / e), s)
        pts.append(cq.Vector(x, y, z))
    return cq.Wire.assembleEdges([cq.Edge.makeSpline(pts, periodic=True)])


def _pchip(xs, ys, x):
    """Monotone cubic (PCHIP) interpolation: no overshoot between stations."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    i = max(0, min(n - 2, sum(1 for xi in xs[1:-1] if xi <= x)))
    t = (x - xs[i]) / h[i]
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]


def loft(sections, k, n_sec=24):
    """sections: list of (x, a, zc, ht, hb, nt, nb) in metres.  The station
    parameters are PCHIP-interpolated onto n_sec evenly spaced sections so the
    B-spline loft follows them without overshoot."""
    cols = list(zip(*sections))
    xs = list(cols[0])
    wires = []
    for j in range(n_sec):
        x = xs[0] + (xs[-1] - xs[0]) * j / (n_sec - 1)
        p = [_pchip(xs, list(c), x) for c in cols[1:]]
        a, zc, ht, hb, nt, nb = p
        wires.append(superellipse_wire(x * k, a * k, zc * k, ht * k, hb * k,
                                       nt, nb))
    return cq.Workplane().add(cq.Solid.makeLoft(wires, ruled=False))


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane().box(x1 - x0, y1 - y0, z1 - z0, centered=False) \
        .translate((x0, y0, z0))


def vcyl(x, y, z0, z1, d):
    """Vertical cylinder from z0 to z1."""
    return cq.Workplane().circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def plate(outline, t):
    """Flat plate in the local XY plane, thickness t centred on z=0."""
    return cq.Workplane().polyline(outline).close().extrude(t).translate((0, 0, -t / 2))


class Fin:
    """A flat surface printed lying flat, glued into a slot in the body.

    outline: planform polygon in local XY (mm); local y=0 is the root line,
             +y points outboard.  The root is extended into the body (negative
             y) and then trimmed by the body so it fits the curved surface.
    tab:     (x0, x1, depth) tab along the root that plugs into a body slot.
    loc:     cq.Location placing local coords onto the vehicle.
    """

    def __init__(self, name, outline, t, tab, loc, qty=1):
        self.name, self.outline, self.t, self.tab, self.loc, self.qty = \
            name, outline, t, tab, loc, qty

    def build(self, body):
        x0, x1, depth = self.tab
        local_body = body.val().moved(self.loc.inverse)
        ext = [(x, y) for (x, y) in self.outline]
        # extend root edge (points with y==0) deep into the body
        ext = [(x, -depth - 8 if abs(y) < 1e-9 else y) for (x, y) in ext]
        lb = cq.Workplane().add(local_body)
        f = plate(ext, self.t).cut(lb)
        # keep only the outboard piece (largest solid)
        f = cq.Workplane().add(max(f.solids().vals(), key=lambda s: s.Volume()))
        # tab = the part of a root strip that lies inside the body
        tab = box(x0, x1, -depth, 6.0, -self.t / 2, self.t / 2).intersect(lb)
        local = f.union(tab)
        slot = box(x0 - CLEAR, x1 + CLEAR, -depth - 0.4, 6.0,
                   -self.t / 2 - CLEAR, self.t / 2 + CLEAR)
        self.local = local
        self.placed = local.val().moved(self.loc)
        self.slot = slot.val().moved(self.loc)
        return self


def split_body(body, z_split, pins, socket=None, extra_upper=None,
               extra_lower=None):
    """Split a body at z = z_split into upper/lower halves, add pin holes
    (list of (x, y)) and an optional stand socket (x, y, z_bottom)."""
    big = 2000
    upper = body.intersect(box(-big, big, -big, big, z_split, big))
    lower = body.intersect(box(-big, big, -big, big, -big, z_split))
    for (x, y) in pins:
        upper = upper.cut(vcyl(x, y, z_split - 0.1, z_split + PIN_DEPTH, PIN_D))
        lower = lower.cut(vcyl(x, y, z_split - PIN_DEPTH, z_split + 0.1, PIN_D))
    if socket:
        x, y, zb = socket
        lower = lower.cut(vcyl(x, y, zb - 5, zb + SOCKET_DEPTH, SOCKET_D))
    return upper, lower


def lay_flat_split(shape, z_split, flip):
    """Orient a body half so its split face sits on the print bed (z=0)."""
    s = shape.translate((0, 0, -z_split))
    if flip:
        s = s.rotate((0, 0, 0), (1, 0, 0), 180)
    return s


def to_bed(shape):
    bb = shape.val().BoundingBox()
    return shape.translate((-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2,
                            -bb.zmin))


def export(name, wp):
    os.makedirs(STL_DIR, exist_ok=True)
    os.makedirs(STEP_DIR, exist_ok=True)
    cq.exporters.export(wp, os.path.join(STL_DIR, name + ".stl"),
                        tolerance=0.03, angularTolerance=0.08)
    cq.exporters.export(wp, os.path.join(STEP_DIR, name + ".step"))
    bb = wp.val().BoundingBox()
    print(f"  {name:32s} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm"
          f"  valid={wp.val().isValid()}")


def stand(label, post_len, base=(110, 60, 5)):
    """Display base with engraved label + separate post with peg."""
    bx, by, bz = base
    b = cq.Workplane().box(bx, by, bz).edges("|Z").fillet(6) \
        .translate((0, 0, bz / 2))
    b = b.faces(">Z").workplane().center(0, -by / 2 + 12) \
        .text(label, 7, -0.8, kind="bold")
    b = b.cut(vcyl(0, 8, 1.2, bz + 1, POST_D + 2 * CLEAR))
    post = cq.Workplane().circle(POST_D / 2).extrude(post_len) \
        .faces(">Z").workplane().circle(PEG_D / 2).extrude(PEG_LEN) \
        .faces(">Z").chamfer(0.6)
    return b, post


# Everything below is collected for preview rendering:
#   ASSEMBLIES[vehicle] = list of (part_name, placed_shape)
ASSEMBLIES = {}


def register(vehicle, parts):
    ASSEMBLIES[vehicle] = parts


# ---------------------------------------------------------------------------
# X-43A Hyper-X  (NASA, Mach 9.6 in Nov 2004)  L = 3.66 m, span 1.53 m
# ---------------------------------------------------------------------------

def build_x43a(scale=24):
    k = 1000.0 / scale
    L = 3.66
    # planform (half width) and side profile -> body = intersection
    plan = [(0.0, 0.012), (1.85, 0.33), (L, 0.33)]
    plan_pts = [(x * k, y * k) for x, y in plan] + \
               [(x * k, -y * k) for x, y in reversed(plan)]
    top = [(0.0, 0.0), (0.35, 0.05), (1.1, 0.12), (2.85, 0.15), (L, 0.10)]
    bot = [(L, -0.08), (2.9, -0.24), (2.0, -0.24), (1.0, -0.10), (0.0, 0.0)]
    prof = [(x * k, z * k) for x, z in top + bot]
    p1 = cq.Workplane("XY").polyline(plan_pts).close().extrude(40 * k, both=True)
    p2 = cq.Workplane("XZ").polyline(prof).close().extrude(40 * k, both=True)
    body = p1.intersect(p2)

    # scramjet module: cowl + sidewalls -> open flow-through duct
    cowl = box(2.08 * k, 2.86 * k, -0.31 * k, 0.31 * k, -0.36 * k, -0.31 * k)
    for s in (1, -1):
        wall = cq.Workplane("XZ").polyline(
            [(2.00 * k, -0.24 * k), (2.86 * k, -0.24 * k),
             (2.86 * k, -0.36 * k), (2.08 * k, -0.36 * k)]).close() \
            .extrude(0.05 * k).translate((0, (0.33 if s > 0 else -0.28) * k, 0))
        cowl = cowl.union(wall)
    body = body.union(cowl)

    fins = []
    # all-moving horizontal "wings" at the split plane (z=0)
    wing = [(0.0, 0.0), (0.75 * k, 0.0), (0.66 * k, 0.43 * k),
            (0.38 * k, 0.43 * k)]
    for side in (1, -1):
        loc = cq.Location(cq.Vector(2.70 * k, side * 0.33 * k, 0))
        if side < 0:
            loc = loc * cq.Location(cq.Vector(), cq.Vector(1, 0, 0), 180)
        fins.append(Fin("x43a_wing", wing, 2.0,
                        (0.15 * k, 0.60 * k, 4.0), loc))
    # twin vertical tails on the aft upper surface
    vt = [(0.0, 0.0), (0.80 * k, 0.0), (0.80 * k, 0.12 * k),
          (0.72 * k, 0.33 * k), (0.45 * k, 0.33 * k)]
    for side in (1, -1):
        loc = cq.Location(cq.Vector(2.86 * k, side * 0.24 * k, 0.11 * k)) * \
            cq.Location(cq.Vector(), cq.Vector(1, 0, 0), 90)
        fins.append(Fin("x43a_vtail", vt, 1.8,
                        (0.15 * k, 0.60 * k, 3.0), loc))

    for f in fins:
        f.build(body)
        body = body.cut(cq.Workplane().add(f.slot))

    pins = [(1.15 * k, 0), (2.4 * k, 0), (3.2 * k, 0)]
    upper, lower = split_body(body, 0.0, pins,
                              socket=(1.65 * k, 0, -0.19 * k))
    parts = [("x43a_body_upper", upper), ("x43a_body_lower", lower)]
    export("x43a_body_upper", lay_flat_split(upper, 0, False))
    export("x43a_body_lower", lay_flat_split(lower, 0, True))
    export("x43a_wing_x2", to_bed(fins[0].local))
    export("x43a_vtail_x2", to_bed(fins[2].local))
    for f in fins:
        parts.append((f.name, cq.Workplane().add(f.placed)))
    b, post = stand("X-43A  1:%d" % scale, 70)
    export("x43a_stand_base", b)
    export("x43a_stand_post", post)
    register("X-43A", parts)


# ---------------------------------------------------------------------------
# X-51A Waverider cruiser (USAF/DARPA/NASA, Mach 5.1 for 210 s, May 2013)
# cruiser L = 4.27 m
# ---------------------------------------------------------------------------

def build_x51a(scale=24):
    k = 1000.0 / scale
    L = 4.27
    sec = [  # x,    a,    zc,   ht,    hb,   nt,  nb
        (0.00, 0.09, 0.00, 0.015, 0.015, 2.0, 2.0),
        (0.30, 0.17, 0.00, 0.045, 0.025, 2.4, 3.0),
        (0.90, 0.24, 0.00, 0.105, 0.045, 2.4, 3.5),
        (1.60, 0.27, 0.00, 0.150, 0.060, 2.3, 3.5),
        (2.50, 0.28, 0.00, 0.170, 0.070, 2.2, 3.5),
        (3.50, 0.27, 0.00, 0.160, 0.070, 2.2, 3.5),
        (L,    0.24, 0.00, 0.140, 0.060, 2.2, 3.5),
    ]
    body = loft(sec, k)
    # ventral scramjet nacelle with open inlet and nozzle
    nac = loft([
        (1.50, 0.17, -0.12, 0.08, 0.06, 4.0, 4.0),
        (2.20, 0.19, -0.13, 0.08, 0.07, 4.0, 4.0),
        (3.60, 0.19, -0.13, 0.08, 0.07, 4.0, 4.0),
        (L,    0.17, -0.12, 0.07, 0.06, 4.0, 4.0),
    ], k)
    body = body.union(nac)
    body = body.cut(box(1.40 * k, 1.85 * k, -0.135 * k, 0.135 * k,
                        -0.165 * k, -0.075 * k))   # inlet
    body = body.cut(box(4.00 * k, L * k + 1, -0.13 * k, 0.13 * k,
                        -0.16 * k, -0.09 * k))     # nozzle

    fins = []
    fin = [(0.0, 0.0), (0.58 * k, 0.0), (0.58 * k, 0.12 * k),
           (0.52 * k, 0.38 * k), (0.32 * k, 0.38 * k)]
    # root line sits at radius 0.14 m on the 45-degree rays (inside the body)
    for ang in (45, 135, 225, 315):
        loc = cq.Location(cq.Vector(3.62 * k, 0, 0.0), cq.Vector(1, 0, 0), ang) * \
            cq.Location(cq.Vector(0, 0.14 * k, 0))
        fins.append(Fin("x51a_fin", fin, 1.8, (0.10 * k, 0.48 * k, 2.5), loc))
    for f in fins:
        f.build(body)
        body = body.cut(cq.Workplane().add(f.slot))

    # pins only where both halves are thick (the forebody lower half is thin)
    pins = [(2.1 * k, 0.12 * k), (2.1 * k, -0.12 * k), (3.5 * k, 0)]
    upper, lower = split_body(body, 0.0, pins,
                              socket=(2.75 * k, 0, -0.20 * k))
    parts = [("x51a_body_upper", upper), ("x51a_body_lower", lower)]
    export("x51a_body_upper", lay_flat_split(upper, 0, False))
    export("x51a_body_lower", lay_flat_split(lower, 0, True))
    # upper and lower fin roots differ (lower ones meet the nacelle)
    export("x51a_fin_upper_x2", to_bed(fins[0].local))
    export("x51a_fin_lower_x2", to_bed(fins[2].local))
    for f in fins:
        parts.append((f.name, cq.Workplane().add(f.placed)))
    b, post = stand("X-51A  1:%d" % scale, 70)
    export("x51a_stand_base", b)
    export("x51a_stand_post", post)
    register("X-51A", parts)


# ---------------------------------------------------------------------------
# HTV-2 Falcon (DARPA hypersonic boost-glide test vehicle, 2010/2011)
# L ~ 3.7 m (approximate; detailed OML not public)
# ---------------------------------------------------------------------------

def build_htv2(scale=24):
    k = 1000.0 / scale
    L = 3.7
    sec = []
    for f in (0.004, 0.02, 0.06, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0):
        x = f * L
        a = 0.015 + 0.52 * f ** 0.85
        ht = 0.012 + 0.40 * f ** 0.95
        hb = 0.006 + 0.04 * f
        sec.append((x, a, hb, ht, hb, 2.2, 6.0))   # zc = hb -> flat bottom z=0
    body = loft(sec, k)
    body = body.intersect(box(-10, L * k + 50, -500, 500, 0.0, 500))
    # two body flaps (lower aft edge)
    for s in (1, -1):
        y0, y1 = sorted((s * 0.08 * k, s * 0.40 * k))
        body = body.union(box((L - 0.05) * k, (L + 0.22) * k, y0, y1,
                              0.0, 0.035 * k))
    body = body.cut(vcyl(2.2 * k, 0, -1, SOCKET_DEPTH, SOCKET_D))
    export("htv2_body", body)
    b, post = stand("HTV-2  1:%d" % scale, 70)
    export("htv2_stand_base", b)
    export("htv2_stand_post", post)
    register("HTV-2", [("htv2_body", body)])


# ---------------------------------------------------------------------------
# North American X-15 (Mach 6.70 in Oct 1967)  L = 15.45 m, span 6.8 m
# ---------------------------------------------------------------------------

def build_x15(scale=72):
    k = 1000.0 / scale
    L = 15.45
    sec = [
        (0.00, 0.03, 0.0, 0.03, 0.03, 2.0, 2.0),
        (0.60, 0.25, 0.0, 0.25, 0.25, 2.0, 2.0),
        (1.60, 0.47, 0.0, 0.46, 0.46, 2.0, 2.0),
        (3.00, 0.68, 0.0, 0.60, 0.60, 2.2, 2.2),
        (4.50, 0.92, 0.0, 0.63, 0.62, 2.6, 2.6),
        (13.5, 0.92, 0.0, 0.63, 0.62, 2.6, 2.6),
        (L,    0.85, 0.0, 0.60, 0.58, 2.6, 2.6),
    ]
    body = loft(sec, k)
    canopy = loft([
        (3.00, 0.05, 0.50, 0.03, 0.03, 2, 2),
        (3.60, 0.32, 0.45, 0.30, 0.20, 2, 2),
        (4.60, 0.30, 0.45, 0.24, 0.20, 2, 2),
        (5.60, 0.06, 0.50, 0.03, 0.03, 2, 2),
    ], k)
    body = body.union(canopy)
    noz = cq.Workplane("YZ").circle(0.38 * k).extrude(0.4 * k) \
        .translate(((L - 0.35) * k, 0, 0))
    body = body.cut(noz)

    fins = []
    wing = [(0.0, 0.0), (2.90 * k, 0.0), (1.80 * k, 2.45 * k),
            (1.17 * k, 2.45 * k)]
    for side in (1, -1):
        loc = cq.Location(cq.Vector(7.3 * k, side * 0.92 * k, 0))
        if side < 0:
            loc = loc * cq.Location(cq.Vector(), cq.Vector(1, 0, 0), 180)
        fins.append(Fin("x15_wing", wing, 1.7, (0.4 * k, 2.4 * k, 5.0), loc))
    htail = [(0.0, 0.0), (2.70 * k, 0.0), (2.55 * k, 1.85 * k),
             (1.85 * k, 1.85 * k)]
    for side in (1, -1):
        loc = cq.Location(cq.Vector(12.4 * k, side * 0.90 * k, 0)) * \
            cq.Location(cq.Vector(), cq.Vector(1, 0, 0), -15 * side)
        if side < 0:
            loc = loc * cq.Location(cq.Vector(), cq.Vector(1, 0, 0), 180)
        fins.append(Fin("x15_htail", htail, 1.7, (0.4 * k, 2.2 * k, 4.0), loc))
    uvt = [(0.0, 0.0), (L * k - 11.4 * k, 0.0), (L * k - 11.4 * k, 1.60 * k),
           (0.95 * k, 1.60 * k)]
    fins.append(Fin("x15_upper_vtail", uvt, 2.2, (0.6 * k, 3.4 * k, 4.0),
                    cq.Location(cq.Vector(11.4 * k, 0, 0.55 * k)) *
                    cq.Location(cq.Vector(), cq.Vector(1, 0, 0), 90)))
    lvt = [(0.0, 0.0), (L * k - 12.2 * k, 0.0), (L * k - 12.2 * k, 1.05 * k),
           (0.75 * k, 1.05 * k)]
    fins.append(Fin("x15_ventral", lvt, 2.2, (0.6 * k, 2.8 * k, 4.0),
                    cq.Location(cq.Vector(12.2 * k, 0, -0.55 * k)) *
                    cq.Location(cq.Vector(), cq.Vector(1, 0, 0), -90)))
    for f in fins:
        f.build(body)
        body = body.cut(cq.Workplane().add(f.slot))

    pins = [(2.6 * k, 0), (6.0 * k, 0), (10.6 * k, 0)]
    upper, lower = split_body(body, 0.0, pins,
                              socket=(8.6 * k, 0, -0.62 * k))
    parts = [("x15_body_upper", upper), ("x15_body_lower", lower)]
    export("x15_body_upper", lay_flat_split(upper, 0, False))
    export("x15_body_lower", lay_flat_split(lower, 0, True))
    export("x15_wing_x2", to_bed(fins[0].local))
    export("x15_htail_x2", to_bed(fins[2].local))
    export("x15_upper_vtail", to_bed(fins[4].local))
    export("x15_ventral_fin", to_bed(fins[5].local))
    for f in fins:
        parts.append((f.name, cq.Workplane().add(f.placed)))
    b, post = stand("X-15  1:%d" % scale, 60)
    export("x15_stand_base", b)
    export("x15_stand_post", post)
    register("X-15", parts)


# ---------------------------------------------------------------------------
# Nonweiler caret waverider -- exact inviscid geometry from oblique-shock
# theory.  The planar shock attaches along both leading edges at the design
# Mach number.
# ---------------------------------------------------------------------------

def shock_angle(M, theta, g=1.4):
    """Weak oblique-shock angle beta (rad) for deflection theta (rad)."""
    def f(b):
        return math.atan(2 / math.tan(b) * (M**2 * math.sin(b)**2 - 1) /
                         (M**2 * (g + math.cos(2 * b)) + 2)) - theta
    lo, hi = math.asin(1 / M) + 1e-6, math.radians(64)
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def build_caret(L=160.0, M=6.0, theta_deg=7.0, span_ratio=0.40):
    th = math.radians(theta_deg)
    beta = shock_angle(M, th)
    s = span_ratio * L
    O = (0, 0, 0)
    U = (L, 0, 0)                       # base, upper centre
    D = (L, 0, -L * math.tan(th))       # base, lower ridge
    Tp = (L, s, -L * math.tan(beta))    # leading-edge tips (on the shock)
    Tm = (L, -s, -L * math.tan(beta))
    V = [cq.Vector(*p) for p in (O, U, D, Tp, Tm)]

    def face(*idx):
        return cq.Face.makeFromWires(cq.Wire.makePolygon([V[i] for i in idx], close=True))

    shell = cq.Shell.makeShell([face(0, 3, 1), face(0, 1, 4),   # upper
                                face(0, 2, 3), face(0, 4, 2),   # lower
                                face(1, 3, 2, 4)])              # base
    solid = cq.Workplane().add(cq.Solid.makeSolid(shell))
    # stand socket into the lower ridge at 60 % length
    xs = 0.6 * L
    zr = -xs * math.tan(th)
    solid = solid.cut(vcyl(xs, 0, zr - 5, zr + SOCKET_DEPTH, SOCKET_D))
    register("Caret waverider", [("caret_waverider", solid)])
    # print standing on its base, nose up
    printed = solid.rotate((0, 0, 0), (0, 1, 0), 90)
    export("caret_waverider", to_bed(printed))
    b, post = stand("CARET M%.0f  %.0f/%.1f" % (M, theta_deg,
                                               math.degrees(beta)), 70)
    export("caret_stand_base", b)
    export("caret_stand_post", post)
    print(f"  caret: M={M}, theta={theta_deg} deg, beta={math.degrees(beta):.2f}"
          f" deg, span={2*s:.1f} mm, base height {L*math.tan(beta):.1f} mm")
    return beta


if __name__ == "__main__":
    for fn in (build_x43a, build_x51a, build_htv2, build_x15, build_caret):
        print(fn.__name__)
        fn()
