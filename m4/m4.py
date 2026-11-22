"""Two-door performance coupe (the user's "M4"), game-level realism, shaped by eye from the user's front/side/rear photos.
Convention (matches wheels.py): forward = -X, left = -Y, up = +Z, metres.
Photo scale: wheelbase 542 px = 3.05 m -> 0.005627 m/px; ground at y=308 px; front axle at x=123 px.
usage: python3 sedan.py [cam names | all] [--samples N] [--res W H]
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
for p in (os.path.join(HERE, '..', 'car'),):          # shared studio.py and wheels.py
    sys.path.insert(0, p)
import studio, wheels

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
car = bpy.data.collections.new('Car'); sc.collection.children.link(car)
cutters = bpy.data.collections.new('Cutters'); sc.collection.children.link(cutters)

AXLE_F, AXLE_R = -1.43, 1.43      # 2.86 m wheelbase
FRONT_X, REAR_X = -2.30, 2.45
DOOR_LINES = (-0.80, 0.66)        # one long coupe door


def principled(name, color, rough=0.4, metal=0.0, coat=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.03
    if emit:
        p.inputs['Emission Color'].default_value = (*emit, 1)
        p.inputs['Emission Strength'].default_value = emit_strength
    return m


def math_node(N, L, op, a, b=None, clamp=False):
    n = N.new('ShaderNodeMath'); n.operation = op; n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            L.new(v, n.inputs[i])
    return n.outputs[0]


def paint_material():
    """Copper-orange metallic + clearcoat, satin-grey hood stripe, dark door shut lines (all in-shader)."""
    m = bpy.data.materials.new('Paint'); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    p = N['Principled BSDF']
    p.inputs['Coat Weight'].default_value = 1.0
    p.inputs['Coat Roughness'].default_value = 0.07
    tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
    X, Y, Z = sep.outputs['X'], sep.outputs['Y'], sep.outputs['Z']
    ay = math_node(N, L, 'ABSOLUTE', Y)
    gm = N.new('ShaderNodeNewGeometry'); sn = N.new('ShaderNodeSeparateXYZ'); L.new(gm.outputs['Normal'], sn.inputs[0])
    # hood stripe: |y| < 0.33, x < -0.85 (hood only), upward-facing
    s1 = math_node(N, L, 'LESS_THAN', ay, 0.33)
    s2 = math_node(N, L, 'LESS_THAN', X, -99.0)
    s3 = math_node(N, L, 'GREATER_THAN', sn.outputs['Z'], 0.6)
    stripe = math_node(N, L, 'MULTIPLY', math_node(N, L, 'MULTIPLY', s1, s2), s3)
    # panel gaps: thin dark shut lines around the doors, bonnet, boot lid and bumpers
    W = 0.004
    nx, nz, ny = sn.outputs['X'], sn.outputs['Z'], math_node(N, L, 'ABSOLUTE', sn.outputs['Y'])
    def near(v, c): return math_node(N, L, 'LESS_THAN', math_node(N, L, 'ABSOLUTE', math_node(N, L, 'SUBTRACT', v, c)), W)
    def between(v, lo, hi): return math_node(N, L, 'MULTIPLY', math_node(N, L, 'GREATER_THAN', v, lo), math_node(N, L, 'LESS_THAN', v, hi))
    def AND(*ms):
        r = ms[0]
        for m_ in ms[1:]: r = math_node(N, L, 'MULTIPLY', r, m_)
        return r
    def OR(*ms):
        r = ms[0]
        for m_ in ms[1:]: r = math_node(N, L, 'MAXIMUM', r, m_)
        return r
    side = math_node(N, L, 'GREATER_THAN', ny, 0.55)
    top = math_node(N, L, 'GREATER_THAN', nz, 0.45)
    back = math_node(N, L, 'GREATER_THAN', nx, 0.45)
    seams = [
        AND(side, OR(near(X, DOOR_LINES[0]), near(X, DOOR_LINES[1])), between(Z, 0.25, 1.01)),   # door front / rear edges
        AND(side, near(Z, 0.255), between(X, DOOR_LINES[0], DOOR_LINES[1])),                    # door bottom
        AND(side, near(X, -2.02), between(Z, 0.30, 0.72)),                                       # front bumper / wing seam
        AND(side, near(X, 2.17), between(Z, 0.30, 0.80)),                                        # rear bumper / quarter seam
        AND(side, near(Z, 0.86), between(X, 1.45, 1.62)), AND(side, near(Z, 0.74), between(X, 1.45, 1.62)),   # fuel flap
        AND(side, OR(near(X, 1.45), near(X, 1.62)), between(Z, 0.74, 0.86)),
        AND(top, near(X, -0.90), between(ay, 0.0, 0.76)),                                        # bonnet rear edge (cowl)
        AND(top, near(ay, 0.76), between(X, -2.18, -0.90)),                                      # bonnet sides
        AND(top, near(X, -2.18), between(ay, 0.0, 0.76)),                                        # bonnet front edge
        AND(top, near(X, 2.02), between(ay, 0.0, 0.74)),                                         # boot lid front edge
        AND(OR(top, back), near(ay, 0.74), between(X, 2.02, 2.50), math_node(N, L, 'GREATER_THAN', Z, 0.70)),   # boot lid sides
        AND(back, near(Z, 0.70), between(ay, 0.0, 0.74)),                                        # boot lid lower edge
        AND(back, near(Z, 0.62), between(ay, 0.74, 0.97)),                                       # rear bumper top seam
    ]
    gap = OR(*seams)
    base = N.new('ShaderNodeMix'); base.data_type = 'RGBA'
    base.inputs[6].default_value = (0.012, 0.15, 0.62, 1); base.inputs[7].default_value = (0.045, 0.045, 0.048, 1)
    L.new(stripe, base.inputs['Factor'])
    col = N.new('ShaderNodeMix'); col.data_type = 'RGBA'; col.inputs[7].default_value = (0.0, 0.0, 0.0, 1)
    L.new(gap, col.inputs['Factor']); L.new(base.outputs[2], col.inputs[6])
    L.new(col.outputs[2], p.inputs['Base Color'])
    dark = math_node(N, L, 'MAXIMUM', stripe, gap)
    for inp, a, b in (('Roughness', 0.38, 0.85), ('Metallic', 0.45, 0.0), ('Coat Weight', 0.9, 0.0)):
        mr = N.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value = a; mr.inputs['To Max'].default_value = b
        L.new(dark, mr.inputs['Value']); L.new(mr.outputs['Result'], p.inputs[inp])
    return m


PAINT = paint_material()
GLASS = principled('Glass', (0.015, 0.018, 0.02), rough=0.02, coat=1.0)
BLACK = principled('GlossBlack', (0.01, 0.01, 0.011), rough=0.15, coat=0.6)
SATIN = principled('SatinBlack', (0.015, 0.015, 0.016), rough=0.55)
CHROME = principled('Chrome', (0.9, 0.9, 0.9), rough=0.06, metal=1.0)
HEAD = principled('HeadLED', (1, 1, 1), emit=(0.85, 0.95, 1.0), emit_strength=12)
HEADLENS = principled('HeadLens', (0.05, 0.055, 0.06), rough=0.05, coat=1.0)
TAIL = principled('TailLED', (0.6, 0.0, 0.0), emit=(1.0, 0.02, 0.01), emit_strength=4)
TAILLENS = principled('TailLens', (0.12, 0.0, 0.0), rough=0.08, coat=1.0)
GRILLE = principled('Grille', (0.006, 0.006, 0.006), rough=0.7)


def link(o, col=car):
    col.objects.link(o); return o


def mesh_from(name, verts, faces, mat, crease_pairs=()):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if crease_pairs:
        cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
        cp = set(crease_pairs)
        for e in bm.edges:
            k = tuple(sorted((e.verts[0].index, e.verts[1].index)))
            if k in cp:
                e[cl] = 1.0
    bm.to_mesh(me); bm.free()
    for f in me.polygons:
        f.use_smooth = True
    o = bpy.data.objects.new(name, me); o.data.materials.append(mat)
    return link(o)


# ---------------------------------------------------------------- body (lower shell) loft
# x, half-width, bottom z, shoulder z, top z   (traced from the photo, widebody flares at the axles)
# x, upper/shoulder half-width, lower/flare half-width, bottom z, shoulder z, top z, door-scoop depth
# Shaped by eye against the user's photos: narrow rounded nose, flares that bulge past it,
# hood sloping down to the nose, beltline rising toward the rear, scooped doors, rounded tail.
STATIONS = [
    (-2.300, 0.690, 0.650, 0.20, 0.620, 0.665, 0.0),
    (-2.260, 0.800, 0.770, 0.15, 0.665, 0.720, 0.0),
    (-2.180, 0.875, 0.865, 0.135, 0.705, 0.765, 0.0),
    (-2.050, 0.915, 0.920, 0.13, 0.745, 0.805, 0.0),
    (-1.800, 0.918, 0.955, 0.13, 0.790, 0.850, 0.0),
    (-1.430, 0.922, 0.968, 0.13, 0.835, 0.895, 0.0),
    (-1.100, 0.925, 0.955, 0.15, 0.865, 0.930, 0.0),
    (-0.800, 0.925, 0.932, 0.17, 0.930, 1.000, 0.015),
    (-0.300, 0.925, 0.940, 0.18, 0.945, 1.020, 0.045),
    (0.400, 0.928, 0.940, 0.18, 0.960, 1.035, 0.045),
    (0.950, 0.932, 0.952, 0.17, 0.980, 1.055, 0.010),
    (1.200, 0.940, 0.978, 0.16, 0.995, 1.070, 0.0),
    (1.430, 0.945, 0.988, 0.155, 1.005, 1.080, 0.0),
    (1.800, 0.940, 0.976, 0.16, 1.010, 1.090, 0.0),
    (2.200, 0.910, 0.930, 0.20, 0.965, 1.050, 0.0),
    (2.360, 0.880, 0.890, 0.24, 0.950, 1.040, 0.0),
    (2.420, 0.820, 0.830, 0.29, 0.930, 1.015, 0.0),
    (2.450, 0.720, 0.730, 0.34, 0.900, 0.975, 0.0),
]

def half_section(ws, wl, zb, zsh, zt, scoop):
    flare = max(0.0, wl - ws - 0.03)
    return [
        (wl - 0.14, zb),
        (wl - 0.03, zb + 0.06),
        (wl, zb + 0.22),                                   # lower body / flare
        (wl - scoop, zb + (zsh - zb) * 0.55),              # door scoop (concave groove between the wheels)
        (ws + 0.005 + flare * 0.75, zsh - 0.07),           # flare carries up toward the shoulder over the wheels
        (ws + 0.014, zsh),                                 # crisp shoulder crease, slightly proud
        (ws - 0.06, zsh + (zt - zsh) * 0.8),
        (ws - 0.27, zt - 0.004),
    ]


NH = 8
SH = 5  # shoulder index in half_section


def _sstep(a, b, v):
    t = min(1.0, max(0.0, (v - a) / (b - a)))
    return t * t * (3 - 2 * t)


BUMPER_PUSH = 0.06


def push(x, z):
    wgt = min(1.0, max(0.0, (-2.13 - x) / 0.17))
    x += 0.09 * wgt * _sstep(0.45, 0.70, z)            # upper part of the nose leans back (raked face)       # only the front-most stations
    lower = _sstep(0.60, 0.46, z)                      # 1 below z=0.50 (bumper), 0 above 0.66 (light band)
    wr = min(1.0, max(0.0, (x - 2.32) / 0.13))
    lower_r = _sstep(0.70, 0.58, z)
    return x - BUMPER_PUSH * wgt * lower + 0.055 * wr * lower_r - 0.06 * wr * _sstep(0.82, 1.0, z)


def ring(st):
    x, ws, wl, zb, zsh, zt, sc = st
    hs = half_section(ws, wl, zb, zsh, zt, sc)
    pts = [(x, 0.0, zb)] + [(x, -y, z) for y, z in hs] + [(x, 0.0, zt)] + [(x, y, z) for y, z in reversed(hs)]
    return [(push(px, pz), py, pz) for px, py, pz in pts]


rings = [ring(s) for s in STATIONS]
n = len(rings[0])
verts = [v for r in rings for v in r]
faces = []
for i in range(len(rings) - 1):
    a, b = i * n, (i + 1) * n
    for j in range(n):
        k = (j + 1) % n
        faces.append((a + j, a + k, b + k, b + j))
c0 = len(verts); verts.append(tuple(sum(v[i] for v in rings[0]) / n for i in range(3)))
c1 = len(verts); verts.append(tuple(sum(v[i] for v in rings[-1]) / n for i in range(3)))
last = (len(rings) - 1) * n
for j in range(n):
    k = (j + 1) % n
    faces.append((c0, k, j)); faces.append((c1, last + j, last + k))
crease_cols = {1 + SH, n - SH - 1 + 1 - 1 + 0}
# column indices of the shoulder crease on both sides
left_sh = 1 + SH
right_sh = NH + 1 + (NH - 1 - SH) + 1
crease_pairs = []
left_ch, right_ch = 1 + 3, NH + 1 + (NH - 1 - 3) + 1     # lower character line (scoop point)
for i in range(len(rings) - 1):
    for col in (left_sh, right_sh, left_ch, right_ch):
        crease_pairs.append(tuple(sorted((i * n + col, (i + 1) * n + col))))
body = mesh_from('Body', verts, faces, PAINT, crease_pairs)
sub = body.modifiers.new('Sub', 'SUBSURF'); sub.levels = 2; sub.render_levels = 2

# wheel arches (widebody): one cutter per wheel, so each well has an inner wall
TIRE_F = wheels.tire_size(285, 30, 21)
TIRE_R = wheels.tire_size(295, 30, 21)
TRACK_Y = 0.815
for ax, (r, w) in ((AXLE_F, TIRE_F), (AXLE_R, TIRE_R)):
    for s in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=r + 0.045, depth=0.95,
                                            location=(ax, s * 1.04, r + 0.015), rotation=(math.pi / 2, 0, 0))
        c = bpy.context.active_object; c.name = 'ArchCut'
        for cc in c.users_collection: cc.objects.unlink(c)
        cutters.objects.link(c); c.hide_render = True; c.display_type = 'WIRE'
        bo = body.modifiers.new('Arch', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.object = c; bo.solver = 'EXACT'
        # dark open-tube liner inside the arch
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=r + 0.04, depth=0.42, end_fill_type='NOTHING',
                                            location=(ax, s * 0.78, r + 0.015), rotation=(math.pi / 2, 0, 0))
        lw = bpy.context.active_object; lw.name = 'Liner'
        for cc in lw.users_collection: cc.objects.unlink(lw)
        car.objects.link(lw); lw.data.materials.append(SATIN)
cutters.hide_render = True

# ---------------------------------------------------------------- greenhouse (traced from the photo)
# x, bottom half-width, top half-width, bottom z (beltline), top z (roof)
GH = [
    (-0.860, 0.860, 0.850, 0.955, 0.960),
    (-0.300, 0.860, 0.660, 1.020, 1.355),
    (0.050, 0.865, 0.680, 1.030, 1.385),
    (0.450, 0.870, 0.680, 1.040, 1.380),
    (0.850, 0.875, 0.665, 1.050, 1.340),
    (1.150, 0.880, 0.640, 1.060, 1.280),
    (1.450, 0.885, 0.610, 1.070, 1.195),
    (1.750, 0.890, 0.580, 1.080, 1.115),
    (2.000, 0.890, 0.560, 1.090, 1.095),
]

def gh_interp(x):
    for k in range(len(GH) - 1):
        if GH[k][0] <= x <= GH[k + 1][0]:
            t = (x - GH[k][0]) / (GH[k + 1][0] - GH[k][0])
            return tuple(GH[k][q] + t * (GH[k + 1][q] - GH[k][q]) for q in range(5))
    return GH[-1]


# finer stations around the rear end of the side window so its curved edge comes out smooth
xs = sorted(set([g[0] for g in GH] + [round(-0.85 + 0.05 * k, 3) for k in range(12)] + [round(0.70 + 0.025 * k, 3) for k in range(19)]))
GHF = [gh_interp(x) for x in xs]

WIN_TOP = 0.64                                   # window top = the user's red outline; blue band above it up to the roof
FR = [0.0, 0.08, 0.16, 0.24, 0.32, 0.40, 0.48, 0.56, WIN_TOP]


def _g(f):                                       # how far the side has leaned in (0 = beltline width, 1 = roof width)
    pts = [(0.0, 0.0), (0.35, 0.40), (0.64, 0.74), (0.93, 1.0)]
    for (f0, g0), (f1, g1) in zip(pts, pts[1:]):
        if f <= f1:
            return g0 + (f - f0) / (f1 - f0) * (g1 - g0)
    return 1.0


def gh_ring(g):
    x, wb, wt, zb, zt = g
    side = [(wb - (wb - wt) * _g(f), zb + (zt - zb) * f) for f in FR] + [(wt, zt - 0.03)]
    left = [(x, -y, z) for y, z in side]
    right = [(x, y, z) for y, z in reversed(side)]
    return left + [(x, -wt * 0.5, zt - 0.004), (x, 0, zt + 0.003), (x, wt * 0.5, zt - 0.004)] + right


grings = [gh_ring(g) for g in GHF]
gn = len(grings[0])
gv = [v for r in grings for v in r]
gf = []
for i in range(len(grings) - 1):
    a_, b_ = i * gn, (i + 1) * gn
    for j in range(gn - 1):
        gf.append((a_ + j, a_ + j + 1, b_ + j + 1, b_ + j))
gh = mesh_from('Greenhouse', gv, gf, GLASS)
gh.data.materials.append(PAINT); gh.data.materials.append(BLACK)
me = gh.data
if sum(f.normal.z for f in me.polygons) < 0:
    for f in me.polygons:
        f.flip()
GLASS_I, PAINT_I, TRIM_I = 0, 1, 2


def window_edge_material():
    """glass in front of the curved rear window edge, body colour behind it (smooth, per pixel)."""
    m = bpy.data.materials.new('WindowEdge'); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    out = N['Material Output']; N.remove(N['Principled BSDF'])
    paint = N.new('ShaderNodeBsdfPrincipled')
    paint.inputs['Base Color'].default_value = (0.012, 0.15, 0.62, 1); paint.inputs['Metallic'].default_value = 0.5
    paint.inputs['Roughness'].default_value = 0.38; paint.inputs['Coat Weight'].default_value = 0.9
    paint.inputs['Coat Roughness'].default_value = 0.03
    glass = N.new('ShaderNodeBsdfPrincipled')
    glass.inputs['Base Color'].default_value = (0.015, 0.018, 0.02, 1); glass.inputs['Roughness'].default_value = 0.02
    glass.inputs['Coat Weight'].default_value = 1.0
    tc = N.new('ShaderNodeTexCoord'); sp = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sp.inputs[0])
    X, Z = sp.outputs['X'], sp.outputs['Z']
    # greenhouse bottom/top heights near the rear door window (linear fit of the stations 0.95..1.30)
    zb = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', math_node(N, L, 'SUBTRACT', X, 0.95), 0.0333), 1.0533)
    zt = math_node(N, L, 'SUBTRACT', 1.322, math_node(N, L, 'MULTIPLY', math_node(N, L, 'SUBTRACT', X, 0.95), 0.20))
    hf = math_node(N, L, 'DIVIDE', math_node(N, L, 'SUBTRACT', Z, zb), math_node(N, L, 'SUBTRACT', zt, zb))
    t = math_node(N, L, 'DIVIDE', hf, WIN_TOP, clamp=True)
    edge = math_node(N, L, 'ADD', 0.78, math_node(N, L, 'MULTIPLY', 0.29,
                     math_node(N, L, 'SQRT', math_node(N, L, 'SUBTRACT', 1.0, math_node(N, L, 'MULTIPLY', t, t), clamp=True))))
    behind = math_node(N, L, 'GREATER_THAN', X, edge)
    mix = N.new('ShaderNodeMixShader')
    L.new(behind, mix.inputs['Fac']); L.new(glass.outputs[0], mix.inputs[1]); L.new(paint.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs['Surface'])
    return m


gh.data.materials.append(window_edge_material())
EDGE_I = 3
NROW = len(FR) - 1                               # side-window rows per side
RAIL_L, RAIL_R = NROW, gn - 2 - NROW             # face column of the body-colour band above each window
X_A = GHF[1][0]                                  # windshield/A-pillar zone ends here


def x_rear(t):
    # curved rear edge of the rear door window (user's red curve): further forward at the top, bulging rearward
    return 0.78 + 0.29 * math.sqrt(max(0.0, 1.0 - t * t))


def x_front(t):
    # front edge of the side window: just behind the A-pillar, leaning back toward the top (user's red outline)
    return -0.62 + 0.20 * t


for fi, f in enumerate(me.polygons):
    i, j = divmod(fi, gn - 1)
    xc = 0.5 * (GHF[i][0] + GHF[i + 1][0])
    if j < NROW or j > RAIL_R:                   # side-window rows
        r = j if j < NROW else (gn - 2 - j)
        t = 0.5 * (FR[r] + FR[r + 1]) / WIN_TOP
        if 0.72 <= xc <= 1.12:
            f.material_index = EDGE_I                # smooth curved rear edge drawn in the shader
        else:
            f.material_index = GLASS_I if x_front(t) < xc < x_rear(t) else PAINT_I   # A-pillar and sail panel blue
    elif j in (RAIL_L, RAIL_R):                  # band between the window top and the roof edge: blue (user's yellow)
        f.material_index = PAINT_I
    else:                                        # roof centre: windshield, black roof, rear window
        f.material_index = GLASS_I if xc < -0.30 else (TRIM_I if xc < 1.10 else GLASS_I)
gs = gh.modifiers.new('Sub', 'SUBSURF'); gs.levels = 1; gs.render_levels = 2
gt = gh.modifiers.new('Thick', 'SOLIDIFY'); gt.thickness = 0.012; gt.offset = -1


def box(name, size, loc, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    from mathutils import Matrix
    o.data.transform(Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    for cc in o.users_collection: cc.objects.unlink(o)
    car.objects.link(o); o.data.materials.append(mat)
    if bevel:
        bv = o.modifiers.new('Bevel', 'BEVEL'); bv.width = bevel; bv.segments = 6
        o.data.polygons.foreach_set('use_smooth', [True] * len(o.data.polygons))
        wn = o.modifiers.new('WN', 'WEIGHTED_NORMAL'); wn.keep_sharp = True
    return o


# black window trim + B-pillar
for s in (-1, 1):
    box('Belt%+d' % s, (1.70, 0.014, 0.02), (0.22, s * 0.872, 1.041), BLACK)

# ---------------------------------------------------------------- front
FX = FRONT_X


def rounded_poly(pts, r, n=6):
    """polygon (y, z) with every corner rounded by a quadratic curve of radius ~r"""
    out = []
    m = len(pts)
    for i in range(m):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % m])
        a_, b_ = p0 - p1, p2 - p1
        s0 = p1 + a_.normalized() * min(r, a_.length * 0.45)
        s1 = p1 + b_.normalized() * min(r, b_.length * 0.45)
        for k in range(n + 1):
            t = k / n
            q = s0 * (1 - t) ** 2 + p1 * (2 * (1 - t) * t) + s1 * (t * t)
            out.append((q.x, q.y))
    return out


def scaled(outline, f):
    cy = sum(p[0] for p in outline) / len(outline); cz = sum(p[1] for p in outline) / len(outline)
    return [(cy + (y - cy) * f, cz + (z - cz) * f) for y, z in outline]


def kidney_solid(name, outline, x0, depth, mat, zpivot, lean, coll=car, bevel=0.0):
    """extrude a (y, z) outline backwards along +X from x0, leaning back by `lean` around z = zpivot"""
    bm = bmesh.new()
    vs = [bm.verts.new((0.0, y, z - zpivot)) for y, z in outline]
    face = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(depth, 0, 0), verts=[e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me_ = bpy.data.meshes.new(name); bm.to_mesh(me_); bm.free()
    o = bpy.data.objects.new(name, me_); o.location = (x0, 0, zpivot); o.rotation_euler = (0, lean, 0)
    coll.objects.link(o); me_.materials.append(mat)
    if bevel:
        bv = o.modifiers.new('Bevel', 'BEVEL'); bv.width = bevel; bv.segments = 3; bv.limit_method = 'ANGLE'
    return o


def honeycomb(name, scale=55.0):
    """black mesh grille: offset-brick cells (reads as honeycomb at game level), mapped on the Y/Z plane."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    p = N['Principled BSDF']; p.inputs['Roughness'].default_value = 0.45
    tc = N.new('ShaderNodeTexCoord'); sp = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sp.inputs[0])
    cb = N.new('ShaderNodeCombineXYZ'); L.new(sp.outputs['Y'], cb.inputs['X']); L.new(sp.outputs['Z'], cb.inputs['Y'])
    br = N.new('ShaderNodeTexBrick'); br.offset = 0.5
    br.inputs['Scale'].default_value = scale
    br.inputs['Color1'].default_value = (0.002, 0.002, 0.002, 1); br.inputs['Color2'].default_value = (0.004, 0.004, 0.004, 1)
    br.inputs['Mortar'].default_value = (0.05, 0.05, 0.055, 1)
    br.inputs['Mortar Size'].default_value = 0.09; br.inputs['Brick Width'].default_value = 0.6; br.inputs['Row Height'].default_value = 0.35
    L.new(cb.outputs[0], br.inputs['Vector']); L.new(br.outputs['Color'], p.inputs['Base Color'])
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.6
    L.new(br.outputs['Fac'], bump.inputs['Height']); L.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m


MESH = honeycomb('Honeycomb', scale=70.0)
for s in (-1, 1):
    # tall grille, one each side of a thin body-colour centre strip: rounded top sloping down toward the headlight,
    # outer side widening toward the bottom, rounded bottom. Cut into the nose, gloss-black frame, mesh, slats.
    LEAN = math.radians(14)
    ZP = 0.43
    base_outline = [(0.035, 0.130), (0.36, 0.200), (0.41, 0.645), (0.27, 0.705), (0.035, 0.690)]
    outline = rounded_poly([(s * y, z) for y, z in base_outline], 0.075)
    if s < 0: outline = outline[::-1]
    cut = kidney_solid('KidneyCut%+d' % s, scaled(outline, 1.04), FX - 0.30, 0.46, GRILLE, ZP, LEAN, coll=cutters, bevel=0)
    cut.hide_render = True; cut.display_type = 'WIRE'
    bo = body.modifiers.new('KidneyHole', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.object = cut; bo.solver = 'EXACT'
    kidney_solid('Kidney%+d' % s, outline, FX + 0.05, 0.10, BLACK, ZP, LEAN, bevel=0.012)
    kidney_solid('KidneyMesh%+d' % s, scaled(outline, 0.90), FX + 0.044, 0.02, GRILLE, ZP, LEAN, bevel=0)
    for k in range(8):
        zz = 0.20 + k * 0.06
        outer = 0.36 + (0.41 - 0.36) * (zz - 0.200) / (0.645 - 0.200) - 0.045
        w = outer - 0.07
        box('Slat%+d_%d' % (s, k), (0.02, w, 0.014), (FX + 0.03 + (zz - ZP) * math.tan(LEAN), s * (0.07 + w / 2), zz), SATIN, rot=(0, LEAN, 0), bevel=0.004)
    # slim angular headlight at the upper corner, inner end lower; L-shaped LED running light
    box('HeadLens%+d' % s, (0.12, 0.34, 0.08), (FX + 0.08, s * 0.59, 0.625), HEADLENS, rot=(s * math.radians(9), 0, s * math.radians(-12)), bevel=0.03)
    box('LEDTop%+d' % s, (0.03, 0.30, 0.010), (FX + 0.02, s * 0.60, 0.65), HEAD, rot=(s * math.radians(9), 0, s * math.radians(-12)))
    box('LEDInner%+d' % s, (0.03, 0.010, 0.05), (FX + 0.006, s * 0.455, 0.605), HEAD)
    for k, yy in enumerate((0.58, 0.69)):
        box('Proj%+d_%d' % (s, k), (0.02, 0.05, 0.032), (FX + 0.0, s * yy, 0.622 + (yy - 0.6) * 0.15), HEAD)
    # big corner intakes with honeycomb, and the vertical air-curtain slit at the outer edge
    box('SideIntake%+d' % s, (0.12, 0.28, 0.16), (FX - 0.01, s * 0.555, 0.29), MESH, rot=(0, 0, s * math.radians(-14)), bevel=0.05)
    box('AirCurtain%+d' % s, (0.10, 0.035, 0.22), (FX + 0.13, s * 0.77, 0.42), GRILLE, rot=(0, 0, s * math.radians(-35)), bevel=0.012)
for s in (-1, 1):
    box('LowerMesh%+d' % s, (0.12, 0.24, 0.10), (FX + 0.0, s * 0.53, 0.245), MESH, bevel=0.035)
# front lip
box('Splitter', (0.30, 1.56, 0.03), (FX + 0.07, 0, 0.165), SATIN, bevel=0.012)
# hood: twin power domes
for s in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=(-1.25, s * 0.30, 0.875))
    hb = bpy.context.active_object; hb.name = 'HoodDome%+d' % s; hb.scale = (0.70, 0.15, 0.03)
    for cc in hb.users_collection: cc.objects.unlink(hb)
    car.objects.link(hb); hb.data.materials.append(PAINT); bpy.ops.object.shade_smooth()

# ---------------------------------------------------------------- sides
for s in (-1, 1):
    box('Mirror%+d' % s, (0.15, 0.10, 0.085), (-0.42, s * 0.975, 1.11), BLACK, bevel=0.04)
    box('MirrorArm%+d' % s, (0.07, 0.08, 0.03), (-0.40, s * 0.905, 1.065), BLACK, bevel=0.01)
    box('Handle%+d' % s, (0.17, 0.012, 0.026), (0.36, s * 0.95, 0.90), PAINT, bevel=0.008)
    box('Skirt%+d' % s, (2.0, 0.05, 0.075), (0.0, s * 0.94, 0.205), BLACK, bevel=0.02)
    box('FenderVent%+d' % s, (0.06, 0.02, 0.26), (-0.93, s * 0.952, 0.62), GRILLE, rot=(0, math.radians(-18), 0), bevel=0.012)

# ---------------------------------------------------------------- rear
RX = REAR_X
PLATEM = principled('PlateWhite', (0.85, 0.86, 0.88), rough=0.35)
REVERSE = principled('ReverseLens', (0.55, 0.57, 0.6), rough=0.05, coat=1.0, emit=(1, 1, 1), emit_strength=0.4)
# lip spoiler on the trunk edge (black)
box('Spoiler', (0.12, 1.30, 0.03), (RX - 0.25, 0, 1.065), BLACK, rot=(0, math.radians(-10), 0), bevel=0.012)
for s_ in (-1, 1):
    # L-shaped tail light: smoked lens across the corner, red LED L inside, wrapping round the side
    box('TailLens%+d' % s_, (0.07, 0.50, 0.11), (RX - 0.03, s_ * 0.56, 0.86), TAILLENS, rot=(s_ * math.radians(-7), 0, 0), bevel=0.035)
    box('TailWrap%+d' % s_, (0.30, 0.05, 0.09), (RX - 0.17, s_ * 0.84, 0.88), TAILLENS, rot=(0, 0, s_ * math.radians(14)), bevel=0.025)
    box('TailL_h%+d' % s_, (0.02, 0.42, 0.014), (RX + 0.01, s_ * 0.58, 0.845), TAIL, rot=(s_ * math.radians(-7), 0, 0))
    box('TailL_v%+d' % s_, (0.02, 0.014, 0.075), (RX + 0.01, s_ * 0.37, 0.86), TAIL)
    box('Reflector%+d' % s_, (0.03, 0.02, 0.17), (RX + 0.03, s_ * 0.80, 0.42), TAILLENS, bevel=0.006)
# plate on the trunk lid between the lights (blank)
box('Plate', (0.012, 0.52, 0.11), (RX + 0.035, 0, 0.78), PLATEM, bevel=0.006)
box('TrunkLine', (0.02, 1.0, 0.012), (RX + 0.012, 0, 0.70), SATIN)
# black diffuser with fins and quad round exhausts (two pairs)
box('Diffuser', (0.36, 1.36, 0.27), (RX - 0.07, 0, 0.255), SATIN, bevel=0.05)
box('RearTrim', (0.30, 1.70, 0.04), (RX - 0.12, 0, 0.11), SATIN, bevel=0.015)
for k, yy in enumerate((-0.48, -0.16, 0.16, 0.48)):
    box('DiffFin%d' % k, (0.22, 0.012, 0.16), (RX - 0.01, yy, 0.18), GLOSSFIN := BLACK)
TIP = principled('TipSteel', (0.78, 0.78, 0.80), rough=0.18, metal=1.0)
DIFF = bpy.data.objects['Diffuser']
for s_ in (-1, 1):
    for k, yy in enumerate((0.27, 0.39)):
        zc, R_, xe = 0.225, 0.05, RX + 0.20            # tip centre height, radius, x of the tip end
        # round opening through the diffuser so the whole tip shows
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=R_ + 0.008, depth=0.6, location=(RX, s_ * yy, zc), rotation=(0, math.pi / 2, 0))
        hc = bpy.context.active_object; hc.name = 'TipHole%+d_%d' % (s_, k)
        for cc in hc.users_collection: cc.objects.unlink(hc)
        cutters.objects.link(hc); hc.hide_render = True
        bo = DIFF.modifiers.new('TipHole', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.object = hc; bo.solver = 'EXACT'
        # polished steel tube with a rolled lip, dark inside
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=R_, depth=0.30, end_fill_type='NOTHING', location=(xe - 0.15, s_ * yy, zc), rotation=(0, math.pi / 2, 0))
        ex = bpy.context.active_object; ex.name = 'Exhaust%+d_%d' % (s_, k)
        for cc in ex.users_collection: cc.objects.unlink(ex)
        car.objects.link(ex); ex.data.materials.append(TIP)
        ex.modifiers.new('Tube', 'SOLIDIFY').thickness = 0.006
        ex.data.polygons.foreach_set('use_smooth', [True] * len(ex.data.polygons))
        bpy.ops.mesh.primitive_torus_add(major_radius=R_, minor_radius=0.007, major_segments=48, minor_segments=10, location=(xe, s_ * yy, zc), rotation=(0, math.pi / 2, 0))
        lip = bpy.context.active_object; lip.name = 'TipLip%+d_%d' % (s_, k)
        for cc in lip.users_collection: cc.objects.unlink(lip)
        car.objects.link(lip); lip.data.materials.append(TIP); lip.data.polygons.foreach_set('use_smooth', [True] * len(lip.data.polygons))
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=R_ - 0.004, depth=0.01, location=(xe - 0.05, s_ * yy, zc), rotation=(0, math.pi / 2, 0))
        ei = bpy.context.active_object; ei.name = 'ExhaustInner%+d_%d' % (s_, k)
        for cc in ei.users_collection: cc.objects.unlink(ei)
        car.objects.link(ei); ei.data.materials.append(GRILLE)

# ---------------------------------------------------------------- wheels: gloss black spokes, red calipers, no logos
wcol = bpy.data.collections.new('Wheels'); car.children.link(wcol)
wheels.ensure_materials()
for mname, colr, metal in (('WHL_Caliper', (0.02, 0.12, 0.55), 0.0), ('WHL_LogoGold', (0.02, 0.02, 0.02), 0.0)):
    mt = bpy.data.materials.get(mname)
    if mt and mt.use_nodes:
        for nd in mt.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED':
                nd.inputs['Base Color'].default_value = (*colr, 1); nd.inputs['Metallic'].default_value = metal
for tag, ax, (r, w), front in (('F', AXLE_F, TIRE_F, True), ('R', AXLE_R, TIRE_R, False)):
    for s, side in ((-1, 'L'), (1, 'R')):
        wheels.build_wheel(tag + side, (ax, s * TRACK_Y, r), r, w, 21, is_left=(s < 0), is_front=front,
                           collection=wcol, spin=math.radians(10 if front else -22),
                           face=dict(hw_root=0.085, hw_tip=0.042, split_pow=1.05, slot_tip=0.34, alpha=15.0, r_hub=0.26))

# ---------------------------------------------------------------- studio + cameras
args = sys.argv[1:]
samples, res = 32, (1280, 720)
if '--samples' in args:
    samples = int(args[args.index('--samples') + 1])
if '--res' in args:
    i = args.index('--res'); res = (int(args[i + 1]), int(args[i + 2]))
objs = studio.setup_studio(sc, samples=samples, res=res, compositor=True)
studio.link_lights_to(objs, car)
# plain skylight (the mullion grid read as patchy stripes in the glass and roof reflections)
sky = bpy.data.materials.get('SkyEmit')
if sky:
    for lk in list(sky.node_tree.links):
        if lk.to_node.type == 'EMISSION' and lk.to_socket.name == 'Color':
            sky.node_tree.links.remove(lk)

CAMS = {
    'side':    ((0.05, -9.4, 0.80), (0.05, 0, 0.66), 50),
    'front34': ((-5.9, -4.2, 1.30), (0.10, 0, 0.68), 50),
    'rear34':  ((5.7, -4.3, 1.45), (0.0, 0, 0.70), 50),
    'front':   ((-9.5, 0.0, 0.62), (0, 0, 0.62), 85),
    'rear':    ((9.5, 0.0, 1.05), (0, 0, 0.62), 85),
    'corner':  ((-4.2, -2.6, 1.05), (-2.2, -0.6, 0.62), 50),
    'tips':    ((RX + 1.7, -0.9, 0.42), (RX, -0.33, 0.24), 50),
    'top34':   ((-4.6, -4.8, 4.3), (0.2, 0, 0.5), 45),
}


def make_cam(name, loc, tgt, lens):
    cd = bpy.data.cameras.new(name); cd.lens = lens
    co = bpy.data.objects.new('Cam_' + name, cd); sc.collection.objects.link(co)
    co.location = loc
    co.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return co


cams = {k: make_cam(k, *v) for k, v in CAMS.items()}
sc.camera = cams['front34']
bpy.ops.wm.save_as_mainfile(filepath=OUT + '/m4.blend')
print('saved blend')
names = list(CAMS) if 'all' in args else [a for a in args if a in CAMS]
for nm in names:
    sc.camera = cams[nm]
    sc.render.filepath = OUT + '/m4_%s.png' % nm
    bpy.ops.render.render(write_still=True)
    print('rendered', nm)
