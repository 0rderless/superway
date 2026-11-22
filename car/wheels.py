"""
wheels.py - Lamborghini Aventador LP700-4 wheel (Dione-style 5 twin-spoke rim,
gloss black), Pirelli-P-Zero-like tyre, carbon-ceramic brake disc and caliper.

COORDINATE CONVENTION (world / car space)
    car forward  = -X
    up           = +Z
    car LEFT side  = -Y      (left wheels:  rim face points -Y)
    car RIGHT side = +Y      (right wheels: rim face points +Y)

API
    build_wheel(name, location, radius_tire, width_tire, rim_diameter_in,
                is_left, is_front, collection=None, **opts) -> root Empty

    location   : centre of the wheel = axle centre on the tyre's mid-plane
                 (so z should normally equal radius_tire for a wheel on the ground).
    radius_tire: tyre outer radius in metres   (255/35 R19 -> 0.3306, 335/30 R20 -> 0.3545)
    width_tire : tyre section width in metres  (0.255 / 0.335)
    rim_diameter_in: 19 / 20
    The root Empty is NOT rotated: it sits at `location` with identity rotation and
    scale, so moving the root moves the whole wheel. Everything hangs below a child
    Empty "<name>_axle" that carries the orientation (local +Z = outward axle axis,
    local +Y = up). The brake caliper always sits at the front-lower part of the
    disc as in the reference, mirrored correctly for left/right wheels.

    optional keywords:
        collection=None  -> collection to link into (default: new collection named `name`)
        spin=0.0         -> rotate rim/tyre/disc about the axle (deg, ccw seen from outside);
                            the caliper stays put (front-lower)
        rim_width=None   -> metres; default 9J for 255 tyres, 12.5J for 335 tyres
        tread=True, lettering=True, face=dict(...) overrides of FACE design params
    Object names: <name> (root Empty), <name>_axle, <name>_spin, <name>_tire, <name>_spokes,
        <name>_barrel, <name>_disc, <name>_caliper, <name>_cap, <name>_logo, <name>_lug0..4 ...
    Rough cost: ~260k vertices per wheel (tyre ~110k with real tread grooves, spoke plate ~140k).

    helpers: tire_size(width_mm, aspect, rim_in) -> (radius, width)
             ensure_materials() -> dict of materials (reused by name if present)

Materials (created once, reused by name):
    WHL_RimGlossBlack, WHL_SatinBlack, WHL_Rubber, WHL_BrakeDisc, WHL_Caliper,
    WHL_LugMetal, WHL_LogoGold, WHL_HubMetal
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

TAU = 2.0 * math.pi

# --------------------------------------------------------------------------- utils


def tire_size(width_mm, aspect, rim_in):
    w = width_mm / 1000.0
    return rim_in * 0.0254 / 2.0 + w * aspect / 100.0, w


def _smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _link(obj, coll, parent):
    coll.objects.link(obj)
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
    return obj


def _mesh_obj(name, verts, faces, mat, coll, parent, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(clean_customdata=False)
    if smooth:
        me.shade_smooth()
    if mat is not None:
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    return _link(ob, coll, parent)


def _lathe(profile, segs, closed_profile=False, start=0.0, sweep=TAU):
    """profile: list of (r, z). returns verts, faces of a surface of revolution
    about local Z.  Full revolution when sweep == TAU."""
    full = abs(sweep - TAU) < 1e-9
    na = segs if full else segs + 1
    n = len(profile)
    verts = []
    for j in range(na):
        a = start + sweep * j / segs
        c, s = math.cos(a), math.sin(a)
        for (r, z) in profile:
            verts.append((r * c, r * s, z))
    faces = []
    nprof = n if closed_profile else n - 1
    for j in range(segs):
        j2 = (j + 1) % na
        for i in range(nprof):
            i2 = (i + 1) % n
            faces.append((j * n + i, j2 * n + i, j2 * n + i2, j * n + i2))
    return verts, faces


def _catmull(pts, per_seg=12):
    out = []
    P = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = (Vector(P[i - 1]), Vector(P[i]), Vector(P[i + 1]), Vector(P[i + 2]))
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            v = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                       (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append((v.x, v.y))
    out.append(tuple(pts[-1]))
    return out


def _resample(poly, step):
    L = [0.0]
    for i in range(1, len(poly)):
        L.append(L[-1] + math.dist(poly[i], poly[i - 1]))
    total = L[-1]
    n = max(2, int(round(total / step)) + 1)
    out = []
    j = 0
    for k in range(n):
        s = total * k / (n - 1)
        while j < len(L) - 2 and L[j + 1] < s:
            j += 1
        seg = L[j + 1] - L[j]
        t = 0.0 if seg < 1e-12 else (s - L[j]) / seg
        a, b = poly[j], poly[j + 1]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


# ----------------------------------------------------------------------- materials


def _principled(name, base, rough, metal=0.0, coat=0.0, coat_rough=0.03, spec=0.5):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    if coat > 0:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = coat_rough
    m.diffuse_color = (*base, 1.0)
    return m, b


def _noise_bump(m, bsdf, scale, strength, distance=0.001):
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 6.0
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = strength
    bp.inputs["Distance"].default_value = distance
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return bp


def _disc_material(name):
    """Carbon-ceramic disc: grey, slightly mottled, with three staggered rows of
    cross-drilled holes (procedural in object space, disc axis = local Z)."""
    m, b = _principled(name, (0.16, 0.16, 0.165), 0.42, metal=0.35, spec=0.5)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])

    def math_node(op, a=None, bval=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        for idx, v in ((0, a), (1, bval)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[idx].default_value = v
            else:
                L.new(v, n.inputs[idx])
        return n.outputs[0]

    x, y = sep.outputs[0], sep.outputs[1]
    r = math_node("SQRT", math_node("ADD", math_node("MULTIPLY", x, x), math_node("MULTIPLY", y, y)))
    th = math_node("ARCTAN2", y, x)
    holes = None
    # rows: (radius, count, phase, hole radius)  -- radii in metres for a ~0.19 m disc
    for (rr, cnt, ph) in ((0.128, 36, 0.0), (0.150, 36, 0.33), (0.172, 36, 0.66)):
        f = math_node("ADD", math_node("MULTIPLY", th, cnt / TAU), ph)
        fr = math_node("SUBTRACT", math_node("FRACT", f), 0.5)
        dt = math_node("MULTIPLY", fr, rr * TAU / cnt)
        dr = math_node("SUBTRACT", r, rr)
        d = math_node("SQRT", math_node("ADD", math_node("MULTIPLY", dt, dt), math_node("MULTIPLY", dr, dr)))
        h = math_node("LESS_THAN", d, 0.0042)
        holes = h if holes is None else math_node("MAXIMUM", holes, h)
    # mottled grey base
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 60.0
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.44, 0.44, 0.45, 1)
    ramp.color_ramp.elements[1].color = (0.58, 0.58, 0.59, 1)
    L.new(nz.outputs["Fac"], ramp.inputs[0])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(holes, mix.inputs["Factor"])
    L.new(ramp.outputs["Color"], mix.inputs[6])
    mix.inputs[7].default_value = (0.005, 0.005, 0.005, 1)
    L.new(mix.outputs[2], b.inputs["Base Color"])
    bp = N.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.8
    bp.inputs["Distance"].default_value = 0.002
    bp.invert = True
    L.new(holes, bp.inputs["Height"])
    L.new(bp.outputs["Normal"], b.inputs["Normal"])
    rough = math_node("ADD", math_node("MULTIPLY", holes, 0.5), 0.42)
    L.new(rough, b.inputs["Roughness"])
    return m


def ensure_materials():
    def get(name, make):
        m = bpy.data.materials.get(name)
        return m if m is not None else make(name)

    mats = {}
    # gloss black paint: very dark base, glossy clear coat -> crisp studio reflections
    mats["rim"] = get("WHL_RimGlossBlack", lambda n: _principled(
        n, (0.040, 0.040, 0.043), 0.18, metal=0.7, coat=1.0, coat_rough=0.02, spec=0.5)[0])
    mats["satin"] = get("WHL_SatinBlack", lambda n: _principled(
        n, (0.018, 0.018, 0.019), 0.48, metal=0.0, spec=0.4)[0])

    def rubber(n):
        m, b = _principled(n, (0.014, 0.014, 0.015), 0.52, spec=0.40)
        _noise_bump(m, b, 900.0, 0.12, 0.0004)
        return m
    mats["rubber"] = get("WHL_Rubber", rubber)
    mats["disc"] = get("WHL_BrakeDisc", _disc_material)
    mats["caliper"] = get("WHL_Caliper", lambda n: _principled(
        n, (0.055, 0.006, 0.005), 0.30, metal=0.0, coat=0.8, coat_rough=0.05)[0])
    mats["lug"] = get("WHL_LugMetal", lambda n: _principled(
        n, (0.70, 0.70, 0.71), 0.32, metal=1.0)[0])
    mats["gold"] = get("WHL_LogoGold", lambda n: _principled(
        n, (0.78, 0.58, 0.24), 0.28, metal=1.0)[0])
    mats["hub"] = get("WHL_HubMetal", lambda n: _principled(
        n, (0.40, 0.40, 0.41), 0.40, metal=0.8)[0])
    return mats


# ------------------------------------------------------------------- 2D polygons


def _clip(poly, p, n):
    """keep the part of polygon where dot(x - p, n) >= 0 (Sutherland-Hodgman)."""
    out = []
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        da = (a[0] - p[0]) * n[0] + (a[1] - p[1]) * n[1]
        db = (b[0] - p[0]) * n[0] + (b[1] - p[1]) * n[1]
        if da >= 0:
            out.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _sector(a0, a1, r0, r1, n=48):
    pts = [(r1 * math.cos(a0 + (a1 - a0) * k / n), r1 * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    pts += [(r0 * math.cos(a1 + (a0 - a1) * k / n), r0 * math.sin(a1 + (a0 - a1) * k / n)) for k in range(n + 1)]
    return pts


def _dedupe(poly, eps=1e-5):
    out = []
    for p in poly:
        if not out or math.dist(p, out[-1]) > eps:
            out.append(p)
    if len(out) > 2 and math.dist(out[0], out[-1]) < eps:
        out.pop()
    return out


def _fillet(poly, rad, max_angle_deg=160.0, nseg=6):
    """round every corner sharper than max_angle with radius rad."""
    poly = _dedupe(poly)
    m = len(poly)
    out = []
    for i in range(m):
        P, V, Nn = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % m])
        d1, d2 = (P - V), (Nn - V)
        l1, l2 = d1.length, d2.length
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        d1 /= l1
        d2 /= l2
        cosang = max(-1.0, min(1.0, d1.dot(d2)))
        ang = math.acos(cosang)
        if math.degrees(ang) > max_angle_deg:
            out.append(tuple(V))
            continue
        t = rad / math.tan(ang / 2)
        t = min(t, 0.45 * l1, 0.45 * l2)
        rr = t * math.tan(ang / 2)
        T1, T2 = V + d1 * t, V + d2 * t
        bis = (d1 + d2).normalized()
        C = V + bis * (rr / math.sin(ang / 2))
        a1 = math.atan2(T1.y - C.y, T1.x - C.x)
        a2 = math.atan2(T2.y - C.y, T2.x - C.x)
        da = (a2 - a1 + math.pi) % TAU - math.pi
        for k in range(nseg + 1):
            a = a1 + da * k / nseg
            out.append((C.x + rr * math.cos(a), C.y + rr * math.sin(a)))
    return _dedupe(out)


def _centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def _line_through(a, b, keep_pt):
    """half-plane bounded by line a-b containing keep_pt -> (p, n)."""
    d = (b[0] - a[0], b[1] - a[1])
    n = (-d[1], d[0])
    if (keep_pt[0] - a[0]) * n[0] + (keep_pt[1] - a[1]) * n[1] < 0:
        n = (-n[0], -n[1])
    return a, n


# ------------------------------------------------------------------- rim face


# Design parameters, normalised to the face radius Rf (inner barrel radius).
# Each of the 5 spokes is a pair of bars ("twin spoke") that share a root near the
# hub and run to the rim with a narrow slot between them; the bars taper, lean and
# bow slightly so the spokes have the swept look of the reference wheel.
FACE = dict(
    n_spokes=5,
    r_hub=0.30,        # big windows never reach inside this radius
    r_out=0.945,       # windows stop here (outer ring 0.945..1)
    lug_r=0.215,       # lug circle radius (PCD 120 mm on a 19")
    lug_hole=0.046,    # lug pocket radius
    a_r=0.26,          # bar root radius
    a_lat=0.030,       # bar root lateral offset from spoke centre line
    b_r=0.99,          # bar end radius
    alpha=13.0,        # bar end angular offset from spoke centre (deg)
    lean=3.0,          # whole spoke tip rotated ccw by this (deg)
    bow=0.000,         # sideways bow of the bars at mid length (ccw +)
    hw_root=0.122,     # bar half width at the root
    hw_tip=0.066,      # bar half width at the rim
    slot_tip=0.42,     # inner end of the slot between the twin bars
    chamfer=0.16,      # chamfer at the outer corners of the big windows
    fillet_win=0.022,
    fillet_slot=0.022,
    split_pow=1.6,     # >1: branches stay merged near the hub and split late (Y)
)


def _bars(F):
    """returns list of bars: (spoke angle, side, centreline pts, half widths).
    Each spoke is a centre line from the hub (radius a_r) to the rim (radius b_r,
    rotated by `lean`); its two branches sit at +-lateral offset w(t) from it, where
    w grows from a_lat at the hub to b_r*sin(alpha) at the rim following t**split_pow
    (split_pow > 1 keeps the branches merged into one broad arm and splits them late:
    a Y-spoke)."""
    bars = []
    n = 56
    p = F.get("split_pow", 1.0)

    def g(t):
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0 + p * (t - 1.0)
        return t ** p

    for k in range(F["n_spokes"]):
        th = math.pi / 2 + TAU * k / F["n_spokes"]
        u = Vector((math.cos(th), math.sin(th)))
        tl = th + math.radians(F["lean"])
        M0 = u * F["a_r"]
        M1 = Vector((math.cos(tl), math.sin(tl))) * F["b_r"] * math.cos(math.radians(F["alpha"]))
        d = (M1 - M0).normalized()
        v = Vector((-d.y, d.x))
        lat_tip = F["b_r"] * math.sin(math.radians(F["alpha"]))
        for s in (-1, 1):
            pts, hws = [], []
            for i in range(n + 1):
                t = -0.35 + 1.6 * i / n
                tt = min(1.0, max(0.0, t))
                w = F["a_lat"] + (lat_tip - F["a_lat"]) * g(t)
                c = M0 + (M1 - M0) * t + v * (s * w + F["bow"] * 4 * tt * (1 - tt))
                pts.append(c)
                hws.append(F["hw_root"] + (F["hw_tip"] - F["hw_root"]) * tt)
            bars.append((th, s, pts, hws))
    return bars


def _edge(bar, toward_side):
    """offset polyline of a bar on side +1 (ccw) or -1 (cw)."""
    _, _, pts, hws = bar
    out = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        d = (b - a).normalized()
        nrm = Vector((-d.y, d.x)) * toward_side
        out.append(pts[i] + nrm * hws[i])
    return out


def _cross(p, q, r, s_):
    """segment intersection p->q with r->s, returns (t, u, point) or None"""
    d1, d2 = q - p, s_ - r
    den = d1.x * d2.y - d1.y * d2.x
    if abs(den) < 1e-12:
        return None
    w = r - p
    t = (w.x * d2.y - w.y * d2.x) / den
    u = (w.x * d1.y - w.y * d1.x) / den
    if 0 <= t <= 1 and 0 <= u <= 1:
        return t, u, p + d1 * t
    return None


def _trunc_out(poly, R):
    """keep polyline (inner->outer) up to its first crossing of radius R."""
    out = [poly[0]]
    for i in range(1, len(poly)):
        a, b = poly[i - 1], poly[i]
        if b.length >= R:
            # interpolate crossing
            lo, hi = 0.0, 1.0
            for _ in range(40):
                m = (lo + hi) / 2
                if (a + (b - a) * m).length < R:
                    lo = m
                else:
                    hi = m
            out.append(a + (b - a) * lo)
            return out
        out.append(b)
    return out


def _trunc_in(poly, R):
    """drop the start of polyline (inner->outer) while radius < R."""
    for i in range(1, len(poly)):
        a, b = poly[i - 1], poly[i]
        if a.length < R <= b.length:
            lo, hi = 0.0, 1.0
            for _ in range(40):
                m = (lo + hi) / 2
                if (a + (b - a) * m).length < R:
                    lo = m
                else:
                    hi = m
            return [a + (b - a) * hi] + poly[i:]
    return poly


def _join_inner(E1, E2):
    """if the two polylines intersect, cut both at the (outermost) crossing."""
    best = None
    for i in range(len(E1) - 1):
        for j in range(len(E2) - 1):
            r = _cross(E1[i], E1[i + 1], E2[j], E2[j + 1])
            if r is not None:
                if best is None or r[2].length > best[2].length:
                    best = (i, j, r[2])
    if best is None:
        return E1, E2, False
    i, j, X = best
    return [X] + E1[i + 1:], [X] + E2[j + 1:], True


def _arc(a0, a1, R, step=0.02):
    da = (a1 - a0 + math.pi) % TAU - math.pi
    n = max(2, int(abs(da) * R / step))
    return [Vector((R * math.cos(a0 + da * k / n), R * math.sin(a0 + da * k / n))) for k in range(1, n)]


def _cut_corner(poly, idx, c1, c2):
    """replace the corner at index idx by a straight chamfer (c1 back, c2 forward)."""
    m = len(poly)

    def walk(start, step, dist):
        acc = 0.0
        i = start
        while True:
            j = (i + step) % m
            seg = (poly[j] - poly[i]).length
            if acc + seg >= dist or j == start:
                t = (dist - acc) / seg if seg > 1e-12 else 0
                return j, poly[i] + (poly[j] - poly[i]) * t
            acc += seg
            i = j
    jb, P1 = walk(idx, -1, c1)
    jf, P2 = walk(idx, 1, c2)
    out = []
    i = jf
    while i != jb:
        out.append(poly[i])
        i = (i + 1) % m
    out.append(poly[jb])
    return out + [P1, P2]


def face_outlines(F=FACE):
    """2D outlines (normalised) of the holes in the spoke plate."""
    bars = _bars(F)
    ns = F["n_spokes"]
    step = TAU / ns
    holes = []
    for k in range(ns):
        th = math.pi / 2 + step * k
        # ---- big window between spoke k (+ bar, ccw side) and spoke k+1 (- bar, cw side)
        E1 = _edge(bars[2 * k + 1], +1)
        E2 = _edge(bars[(2 * k + 2) % (2 * ns)], -1)
        E1, E2, joined = _join_inner(E1, E2)
        if not joined:
            E1, E2 = _trunc_in(E1, F["r_hub"]), _trunc_in(E2, F["r_hub"])
        else:
            if E1[0].length < F["r_hub"]:
                E1, E2 = _trunc_in(E1, F["r_hub"]), _trunc_in(E2, F["r_hub"])
                joined = False
        E1, E2 = _trunc_out(E1, F["r_out"]), _trunc_out(E2, F["r_out"])
        a1 = math.atan2(E1[-1].y, E1[-1].x)
        a2 = math.atan2(E2[-1].y, E2[-1].x)
        poly = list(E1)
        c1 = len(poly) - 1
        poly += _arc(a1, a2, F["r_out"])
        c2 = len(poly)
        poly += list(reversed(E2))
        if not joined:
            b1 = math.atan2(E2[0].y, E2[0].x)
            b0 = math.atan2(E1[0].y, E1[0].x)
            poly += _arc(b1, b0, F["r_hub"])
        # chamfers (second one first so the first index stays valid)
        poly = _cut_corner(poly, c2, F["chamfer"], F["chamfer"] * 0.8)
        # find the E1 corner again: point closest to E1 end
        ci = min(range(len(poly)), key=lambda i: (poly[i] - E1[-1]).length)
        poly = _cut_corner(poly, ci, F["chamfer"], F["chamfer"] * 0.8)
        poly = _fillet([tuple(p) for p in poly], F["fillet_win"])
        holes.append(poly)
        # ---- slot between the twin bars of spoke k
        S1 = _edge(bars[2 * k], +1)
        S2 = _edge(bars[2 * k + 1], -1)
        S1, S2, joined = _join_inner(S1, S2)
        if not joined or S1[0].length < F["slot_tip"]:
            S1, S2 = _trunc_in(S1, F["slot_tip"]), _trunc_in(S2, F["slot_tip"])
            joined = False
        S1, S2 = _trunc_out(S1, F["r_out"]), _trunc_out(S2, F["r_out"])
        a1 = math.atan2(S1[-1].y, S1[-1].x)
        a2 = math.atan2(S2[-1].y, S2[-1].x)
        poly = list(S1) + _arc(a1, a2, F["r_out"]) + list(reversed(S2))
        poly = _fillet([tuple(p) for p in poly], F["fillet_slot"])
        holes.append(poly)
        # ---- lug pocket
        lc = (F["lug_r"] * math.cos(th), F["lug_r"] * math.sin(th))
        holes.append([(lc[0] + F["lug_hole"] * math.cos(a), lc[1] + F["lug_hole"] * math.sin(a))
                      for a in [TAU * i / 32 for i in range(32)]])
    return holes


def _build_face(name, Rf, top_z, thick, dish, crown, mat, coll, parent, F=FACE):
    cu = bpy.data.curves.new(name + "_crv", "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    bev = min(0.007, thick * 0.2)
    cu.extrude = thick / 2 - bev
    cu.bevel_depth = bev
    cu.bevel_resolution = 1

    def add(pts):
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, (x, y) in enumerate(pts):
            sp.points[i].co = (x * Rf, y * Rf, 0.0, 1.0)
        sp.use_cyclic_u = True

    add([(1.0 * math.cos(a), 1.0 * math.sin(a)) for a in [TAU * i / 180 for i in range(180)]])
    for h in face_outlines(F):
        add(h)
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    coll.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.name = name
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    # densify for the dish deformation
    mod = ob.modifiers.new("dens", "SUBSURF")
    mod.subdivision_type = "SIMPLE"
    mod.levels = 2
    mod.render_levels = 2
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    ob.data = me2
    bpy.data.meshes.remove(me)
    me2.name = name
    bars = _bars(F)
    segs = []
    for (_, _, pts, hws) in bars:
        sub = pts[::6] + ([pts[-1]] if (len(pts) - 1) % 6 else [])
        for i in range(len(sub) - 1):
            segs.append((sub[i] * Rf, sub[i + 1] * Rf))
    hw = 0.5 * (F["hw_root"] + F["hw_tip"]) * Rf

    import numpy as np
    SA = np.array([[A.x, A.y] for (A, B) in segs])
    SB = np.array([[B.x, B.y] for (A, B) in segs])
    SD = SB - SA
    SL = (SD * SD).sum(1)

    def sstep(a, b, x):
        t = np.clip((x - a) / (b - a), 0.0, 1.0)
        return t * t * (3 - 2 * t)

    def offset(X, Y):
        R = np.hypot(X, Y) / Rf
        off = -dish * (1.0 - sstep(0.30, 0.985, R))
        if crown > 0:
            acc = np.zeros_like(X)
            for i in range(len(SA)):
                px, py = X - SA[i, 0], Y - SA[i, 1]
                t = np.clip((px * SD[i, 0] + py * SD[i, 1]) / SL[i], 0.0, 1.0)
                dx, dy = px - SD[i, 0] * t, py - SD[i, 1] * t
                dd = np.sqrt(dx * dx + dy * dy) / (hw * 1.25)
                acc = np.maximum(acc, np.where(dd < 1.0, 1.0 - dd * dd, 0.0))
            off = off + crown * acc * sstep(0.30, 0.42, R) * (1 - sstep(0.90, 0.99, R))
        return off

    me2.update()
    nv = len(me2.vertices)
    co = np.empty(nv * 3)
    me2.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    X, Y = co[:, 0].copy(), co[:, 1].copy()
    eps = 0.0008
    O = offset(X, Y)
    GX = (offset(X + eps, Y) - offset(X - eps, Y)) / (2 * eps)
    GY = (offset(X, Y + eps) - offset(X, Y - eps)) / (2 * eps)
    npoly = len(me2.polygons)
    pn = np.empty(npoly * 3)
    me2.polygons.foreach_get("normal", pn)          # flat plate: before deforming
    pnz = pn.reshape(-1, 3)[:, 2]
    co[:, 2] += top_z - thick / 2 + O
    me2.vertices.foreach_set("co", co.ravel())
    sign = np.where(pnz > 0.9995, 1.0, np.where(pnz < -0.9995, -1.0, 0.0))
    ls = np.empty(npoly, dtype=np.int32)
    me2.polygons.foreach_get("loop_start", ls)
    lt = np.empty(npoly, dtype=np.int32)
    me2.polygons.foreach_get("loop_total", lt)
    nl = len(me2.loops)
    lv = np.empty(nl, dtype=np.int32)
    me2.loops.foreach_get("vertex_index", lv)
    lsign = np.repeat(sign, lt)
    N = np.stack([-GX[lv], -GY[lv], np.ones(nl)], 1)
    N /= np.linalg.norm(N, axis=1)[:, None]
    N *= lsign[:, None]
    loop_normals = [tuple(x) for x in N]
    me2.shade_smooth()
    try:
        me2.normals_split_custom_set(loop_normals)
    except Exception as ex:
        print("custom normals failed", ex)
    me2.materials.clear()
    me2.materials.append(mat)
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)
    return ob


# ------------------------------------------------------------------------ tyre


def _tire(name, Rt, Wt, Rr, hw_rim, mats, coll, parent, tread=True, n_pitch=None):
    ht = Wt / 2.0
    H = Rt - Rr
    ctrl = [
        (Rr + 0.006, hw_rim - 0.004),
        (Rr + 0.020, hw_rim + 0.008),
        (Rr + 0.030, ht - 0.002),
        (Rr + 0.30 * H, ht + 0.001),
        (Rr + 0.62 * H, ht - 0.001),
        (Rt - 0.022, ht - 0.006),
        (Rt - 0.010, ht - 0.014),
        (Rt - 0.003, ht - 0.030),
        (Rt - 0.0008, ht * 0.55),
        (Rt, 0.0),
    ]
    half = _catmull(ctrl, 16)
    half = _resample(half, 0.0019)
    other = [(r, -z) for (r, z) in reversed(half[:-1])]
    prof = half + other            # outer bead -> tread centre -> inner bead
    n = len(prof)
    # profile normals (outward)
    norms = []
    for i in range(n):
        a = prof[max(0, i - 1)]
        b = prof[min(n - 1, i + 1)]
        tr, tz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tr, tz) or 1.0
        nr, nz = tz / L, -tr / L     # rotate tangent (pointing toward -z side)
        if nr < 0 and abs(prof[i][1]) < ht * 0.5:
            nr, nz = -nr, -nz
        norms.append((nr, nz))
    # fix orientation: normals should point away from (Rr+H/2, 0)
    for i in range(n):
        r, z = prof[i]
        nr, nz = norms[i]
        if (r - (Rr + 0.45 * H)) * nr + z * nz < 0:
            norms[i] = (-nr, -nz)
    # arc-length from tread centre (signed, + = outer side)
    ic = len(half) - 1
    sarc = [0.0] * n
    for i in range(ic + 1, n):
        sarc[i] = sarc[i - 1] - math.dist(prof[i], prof[i - 1])
    for i in range(ic - 1, -1, -1):
        sarc[i] = sarc[i + 1] + math.dist(prof[i], prof[i + 1])
    # tread edge (start of shoulder roll) in arc length
    s_edge = ht - 0.026
    circ = [0.34, -0.06, -0.44] if Wt < 0.3 else [0.40, 0.08, -0.22, -0.52]
    circ_w = 0.0050
    depth = 0.0065
    if n_pitch is None:
        n_pitch = int(round(TAU * Rt / 0.058))
    gf = 0.10
    fr = [0.0, 0.02, gf - 0.02, gf, 0.2, 0.3, 0.4, 0.5, 0.52, 0.5 + gf - 0.02, 0.5 + gf, 0.7, 0.8, 0.9]
    if not tread:
        fr = [k / 6 for k in range(6)]
    angs = [TAU * (p + f) / n_pitch for p in range(n_pitch) for f in fr]
    nf = len(fr)

    def disp(i, j):
        if not tread:
            return 0.0
        s = sarc[i]
        d = 0.0
        # circumferential grooves (only on the tread)
        for c in circ:
            if abs(s - c * ht) < circ_w:
                d = depth
        f = fr[j % nf]
        in_outer = 0.01 < f < gf - 0.01
        in_inner = 0.51 < f < 0.5 + gf - 0.01
        # outer shoulder lateral grooves: from the outer circ groove out over the shoulder
        if in_outer and (0.42 * ht) < s < (ht + 0.012):
            fade = 1.0 - _smoothstep(ht - 0.004, ht + 0.012, s)
            d = max(d, depth * fade)
        # inner half: short shallow sipes only (P Zero inner side is mostly closed)
        if in_inner and -(0.92 * ht) < s < -(0.62 * ht):
            d = max(d, depth * 0.45)
        # thin sipes in the centre ribs (half depth)
        if (0.0 < f < 0.02) and (-0.30 * ht < s < 0.30 * ht) and d == 0.0 and Wt >= 0:
            d = depth * 0.25
        return d

    verts = []
    for j, a in enumerate(angs):
        c, s_ = math.cos(a), math.sin(a)
        for i in range(n):
            r, z = prof[i]
            d = disp(i, j)
            nr, nz = norms[i]
            rr, zz = r - nr * d, z - nz * d
            verts.append((rr * c, rr * s_, zz))
    na = len(angs)
    faces = []
    for j in range(na):
        j2 = (j + 1) % na
        for i in range(n - 1):
            faces.append((j * n + i, j * n + i + 1, j2 * n + i + 1, j2 * n + i))
    ob = _mesh_obj(name, verts, faces, mats["rubber"], coll, parent)
    # crisp groove walls: mark steep edges sharp via smooth-by-angle
    try:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.normal_update()
        for e in bm.edges:
            if len(e.link_faces) == 2:
                if e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > math.radians(50):
                    e.smooth = False
        bm.to_mesh(me)
        bm.free()
    except Exception:
        pass
    return ob, prof


def _lettering(name, prof, Rr, Rt, mats, coll, parent, texts=("PIRELLI", "P ZERO"), height=0.0125):
    """subtle raised lettering on the outer sidewall."""
    H = Rt - Rr
    rc = Rr + 0.52 * H
    # z of the outer sidewall as a function of r (outer half of the profile)
    outer = [(r, z) for (r, z) in prof if z > 0]
    outer_sw = [p for p in outer if p[0] < Rt - 0.03]

    def zof(r):
        best = min(outer_sw, key=lambda p: abs(p[0] - r))
        return best[1]

    objs = []
    for k, (txt, a0) in enumerate(((texts[0], 90.0), (texts[1], -30.0), (texts[0], 210.0))):
        cu = bpy.data.curves.new(f"{name}_txt{k}", "FONT")
        cu.body = txt
        cu.size = height
        cu.extrude = 0.0
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.resolution_u = 3
        tmp = bpy.data.objects.new("tmp", cu)
        coll.objects.link(tmp)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
        bpy.data.objects.remove(tmp)
        bpy.data.curves.remove(cu)
        bm = bmesh.new()
        bm.from_mesh(me)
        ret = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
        for v in [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]:
            v.co.z += 0.0007
        th0 = math.radians(a0)
        for v in bm.verts:
            x, y, z = v.co
            ang = th0 - x / rc
            rad = rc + y
            zz = zof(rad) - 0.0003 + z
            v.co = (rad * math.cos(ang), rad * math.sin(ang), zz)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats["rubber"])
        ob = bpy.data.objects.new(f"{name}_letter{k}", me)
        objs.append(_link(ob, coll, parent))
    return objs


# ------------------------------------------------------------------- brakes


def _caliper(name, r_disc, z_disc, ang, mats, coll, parent, front=True, r_max=1e9):
    """a curved monoblock caliper straddling the disc, centred at local angle ang."""
    r0, r1 = r_disc - 0.050, min(r_disc + 0.017, r_max)
    span = math.radians(48 if front else 40)
    zt = 0.055 if front else 0.050
    segs = 16
    bm = bmesh.new()
    # build as a curved box: rings in (r, z) cross-section swept along the arc
    sec = [(r0, -zt), (r1, -zt), (r1, zt), (r0, zt)]
    rings = []
    for j in range(segs + 1):
        a = ang - span / 2 + span * j / segs
        # taper the ends slightly (rounded outline)
        e = abs(j / segs - 0.5) * 2
        shrink = 0.012 * e ** 3
        ring = []
        for (r, z) in sec:
            rr = r + (shrink if r == r0 else -shrink * 0.4)
            zz = z * (1 - 0.15 * e ** 3)
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z_disc + zz)))
        rings.append(ring)
    for j in range(segs):
        for i in range(4):
            bm.faces.new((rings[j][i], rings[j + 1][i], rings[j + 1][(i + 1) % 4], rings[j][(i + 1) % 4]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["caliper"])
    ob = _link(bpy.data.objects.new(name, me), coll, parent)
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width = 0.008
    bv.segments = 3
    bv.limit_method = "ANGLE"
    sub = ob.modifiers.new("sub", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    me.shade_smooth()
    # slot between the two halves facing outward (dark recess)
    return ob


def _disc(name, r_out, r_in, z, thick, mats, coll, parent):
    prof = [(r_in, z - thick / 2), (r_out - 0.002, z - thick / 2), (r_out, z - thick / 2 + 0.002),
            (r_out, z + thick / 2 - 0.002), (r_out - 0.002, z + thick / 2), (r_in, z + thick / 2)]
    v, f = _lathe(prof, 144, closed_profile=True)
    ob = _mesh_obj(name, v, f, mats["disc"], coll, parent, smooth=False)
    # outer rim faces smooth-looking enough at 144 segs
    return ob


# ---------------------------------------------------------------------- build


def build_wheel(name, location, radius_tire, width_tire, rim_diameter_in, is_left, is_front,
                collection=None, rim_width=None, tread=True, lettering=True, face=None, spin=0.0):
    mats = ensure_materials()
    if collection is None:
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(collection)
    coll = collection
    F = dict(FACE)
    if face:
        F.update(face)

    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.2
    root.location = Vector(location)
    coll.objects.link(root)
    axle = bpy.data.objects.new(name + "_axle", None)
    axle.empty_display_size = 0.1
    _link(axle, coll, root)
    # local X,Y,Z -> world columns
    if is_left:
        M = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))     # cols: X->+X, Y->+Z, Z->-Y
    else:
        M = Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0)))     # cols: X->-X, Y->+Z, Z->+Y
    axle.rotation_euler = M.to_euler("XYZ")
    # rotating part (rim, tyre, disc) under "<name>_spin"; spin in degrees,
    # positive = counter-clockwise seen from outside. Caliper/upright do not spin.
    rot = bpy.data.objects.new(name + "_spin", None)
    rot.empty_display_size = 0.05
    _link(rot, coll, axle)
    rot.rotation_euler = (0.0, 0.0, math.radians(spin))

    # ---- dimensions
    Rr = rim_diameter_in * 0.0254 / 2.0            # bead seat radius
    if rim_width is None:
        w_in = round(2 * (width_tire / 0.0254 - (1.0 if width_tire < 0.3 else 0.7))) / 2
        rim_width = w_in * 0.0254
    hw = rim_width / 2.0
    Rf = Rr - 0.012                                 # inner barrel radius = face radius
    lip_front = hw + 0.012
    face_top = hw + 0.004
    thick = 0.044 if is_front else 0.048
    dish = 0.032 if is_front else 0.055
    crown = 0.0

    # ---- rim barrel + lip (lathe)
    prof = [
        (Rf - 0.004, face_top - 0.006),
        (Rf + 0.001, lip_front - 0.002),
        (Rf + 0.006, lip_front),
        (Rr + 0.008, lip_front + 0.0005),
        (Rr + 0.015, lip_front - 0.002),
        (Rr + 0.018, lip_front - 0.008),
        (Rr + 0.016, hw - 0.001),
        (Rr + 0.004, hw - 0.006),
        (Rr, hw - 0.020),
        (Rr - 0.006, hw - 0.045),
        (Rr - 0.006, -hw + 0.035),
        (Rr, -hw + 0.015),
        (Rr + 0.004, -hw + 0.004),
        (Rr + 0.014, -hw - 0.001),
        (Rr + 0.012, -hw - 0.008),
        (Rf - 0.002, -hw - 0.008),
        (Rf - 0.010, -hw - 0.002),
        (Rf - 0.010, face_top - thick - 0.002),
    ]
    v, f = _lathe(prof, 180, closed_profile=True)
    barrel = _mesh_obj(name + "_barrel", v, f, mats["rim"], coll, rot)
    # crisp edges via bevel-less auto-sharp: mark sharp edges at strong profile corners
    bm = bmesh.new()
    bm.from_mesh(barrel.data)
    bm.normal_update()
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > math.radians(55):
            e.smooth = False
    bm.to_mesh(barrel.data)
    bm.free()

    # ---- spoke plate
    _build_face(name + "_spokes", Rf + 0.002, face_top, thick, dish, crown, mats["rim"], coll, rot, F)

    hub_top = face_top - dish
    hub_back = hub_top - thick
    # ---- hub plate behind the spokes (closes lug pockets)
    v, f = _lathe([(0.0, hub_back - 0.004), (0.42 * Rf, hub_back - 0.004), (0.42 * Rf, hub_back + 0.006),
                   (0.0, hub_back + 0.006)], 64, closed_profile=False)
    _mesh_obj(name + "_hubplate", v, f, mats["satin"], coll, rot)

    # ---- lug bolts
    for k in range(F["n_spokes"]):
        th = math.pi / 2 + TAU * k / F["n_spokes"]
        cx, cy = F["lug_r"] * Rf * math.cos(th), F["lug_r"] * Rf * math.sin(th)
        rr = F["lug_hole"] * Rf
        zb = hub_back + 0.006
        zt = hub_top - 0.011
        # washer + hex head
        prof_w = [(0.0, zb), (rr * 0.85, zb), (rr * 0.85, zb + 0.004), (rr * 0.62, zb + 0.004)]
        v, f = _lathe(prof_w, 24)
        _mesh_obj(f"{name}_lugwasher{k}", [(x + cx, y + cy, z) for (x, y, z) in v], f, mats["lug"], coll, rot)
        hexr = 0.0125
        prof_h = [(hexr, zb + 0.004), (hexr, zt - 0.0015), (hexr - 0.0015, zt), (0.0, zt)]
        v, f = _lathe(prof_h, 6, start=th)
        _mesh_obj(f"{name}_lug{k}", [(x + cx, y + cy, z) for (x, y, z) in v], f, mats["lug"], coll, rot,
                  smooth=False)

    # ---- centre cap with logo
    cap_r = 0.150 * Rf
    capz = hub_top + 0.002
    v, f = _lathe([(0.0, capz + 0.004), (cap_r * 0.6, capz + 0.0035), (cap_r - 0.002, capz + 0.002),
                   (cap_r, capz - 0.001), (cap_r, hub_back)], 48)
    _mesh_obj(name + "_cap", v, f, mats["rim"], coll, rot)
    # shield logo (gold): pentagon-ish shield outline
    sh = [(-0.5, 0.5), (0.5, 0.5), (0.48, -0.05), (0.3, -0.38), (0.0, -0.55), (-0.3, -0.38), (-0.48, -0.05)]
    sc = cap_r * 0.95
    cu = bpy.data.curves.new(name + "_logo", "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = 0.0006
    sp = cu.splines.new("POLY")
    sp.points.add(len(sh) - 1)
    # orient the logo upright in world (local +Y = up for both sides)
    for i, (x, y) in enumerate(sh):
        sp.points[i].co = (x * sc * 0.82, y * sc, 0, 1)
    sp.use_cyclic_u = True
    logo = bpy.data.objects.new(name + "_logo", cu)
    logo.location = (0, 0, capz + 0.0045)
    logo.data.materials.append(mats["gold"])
    _link(logo, coll, rot)
    # inner black bull silhouette hint: a dark smaller shield inset
    cu2 = cu.copy()
    cu2.materials.clear()
    cu2.materials.append(mats["rim"])
    inner = bpy.data.objects.new(name + "_logo_in", cu2)
    inner.scale = (0.55, 0.55, 1.0)
    inner.location = (0, -0.0006, capz + 0.0052)
    _link(inner, coll, rot)

    # ---- brake disc, bell, caliper
    r_disc = min(0.200 if is_front else 0.190, Rf - 0.016)
    z_disc = hub_back - 0.050
    dthick = 0.038 if is_front else 0.036
    disc = _disc(name + "_disc", r_disc, r_disc * 0.56, z_disc, dthick, mats, coll, rot)
    # scale the procedural drill pattern to the disc size
    disc.data  # pattern rows are in metres for ~0.19 disc; fine for 0.19-0.20
    v, f = _lathe([(0.0, hub_back - 0.004), (0.085, hub_back - 0.004), (0.095, hub_back - 0.012),
                   (0.098, z_disc + dthick / 2), (r_disc * 0.58, z_disc + dthick / 2 - 0.004),
                   (r_disc * 0.58, z_disc - dthick / 2), (0.09, z_disc - dthick / 2)], 72)
    _mesh_obj(name + "_bell", v, f, mats["hub"], coll, rot)
    # caliper at front-lower (psi measured from forward toward up)
    psi = math.radians(-22.0)
    ang = (math.pi - psi) if is_left else psi
    _caliper(name + "_caliper", r_disc, z_disc, ang, mats, coll, axle, is_front, r_max=Rf - 0.006)
    # dark upright/knuckle hint behind the disc
    v, f = _lathe([(0.0, z_disc - dthick / 2 - 0.03), (0.13, z_disc - dthick / 2 - 0.03),
                   (0.13, z_disc - dthick / 2 - 0.08), (0.0, z_disc - dthick / 2 - 0.08)], 40)
    _mesh_obj(name + "_upright", v, f, mats["satin"], coll, axle)

    # ---- tyre
    Rt = radius_tire
    tire, tprof = _tire(name + "_tire", Rt, width_tire, Rr, hw, mats, coll, rot, tread=tread)
    if lettering:
        _lettering(name, tprof, Rr, Rt, mats, coll, rot)
    return root


if __name__ == "__main__":
    pass
