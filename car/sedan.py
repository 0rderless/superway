"""Widebody 4-door muscle sedan, game-level realism, proportions traced from the user's side photo.
Convention (matches wheels.py): forward = -X, left = -Y, up = +Z, metres.
Photo scale: wheelbase 542 px = 3.05 m -> 0.005627 m/px; ground at y=308 px; front axle at x=123 px.
usage: python3 sedan.py [cam names | all] [--samples N] [--res W H]
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))   # studio.py and wheels.py live next to this script
OUT = os.path.join(HERE, 'out')
for p in (HERE,):
    sys.path.insert(0, p)
import studio, wheels

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
car = bpy.data.collections.new('Car'); sc.collection.children.link(car)
cutters = bpy.data.collections.new('Cutters'); sc.collection.children.link(cutters)

AXLE_F, AXLE_R = -1.525, 1.525
FRONT_X, REAR_X = -2.25, 2.41
DOOR_LINES = (-0.86, 0.36, 1.30)   # front door leading edge, B-pillar, rear door trailing edge


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
    p.inputs['Coat Roughness'].default_value = 0.03
    tc = N.new('ShaderNodeTexCoord'); sep = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sep.inputs[0])
    X, Y, Z = sep.outputs['X'], sep.outputs['Y'], sep.outputs['Z']
    ay = math_node(N, L, 'ABSOLUTE', Y)
    gm = N.new('ShaderNodeNewGeometry'); sn = N.new('ShaderNodeSeparateXYZ'); L.new(gm.outputs['Normal'], sn.inputs[0])
    # hood stripe: |y| < 0.33, x < -0.85 (hood only), upward-facing
    s1 = math_node(N, L, 'LESS_THAN', ay, 0.33)
    s2 = math_node(N, L, 'LESS_THAN', X, -0.85)
    s3 = math_node(N, L, 'GREATER_THAN', sn.outputs['Z'], 0.6)
    stripe = math_node(N, L, 'MULTIPLY', math_node(N, L, 'MULTIPLY', s1, s2), s3)
    # door shut lines on the body side: |x - Xi| < 4 mm, side-facing, between sill and beltline
    side = math_node(N, L, 'GREATER_THAN', math_node(N, L, 'ABSOLUTE', sn.outputs['Y']), 0.55)
    zr = math_node(N, L, 'MULTIPLY', math_node(N, L, 'GREATER_THAN', Z, 0.24), math_node(N, L, 'LESS_THAN', Z, 0.96))
    lines = None
    for xi in DOOR_LINES:
        d = math_node(N, L, 'LESS_THAN', math_node(N, L, 'ABSOLUTE', math_node(N, L, 'SUBTRACT', X, xi)), 0.004)
        lines = d if lines is None else math_node(N, L, 'MAXIMUM', lines, d)
    gap = math_node(N, L, 'MULTIPLY', math_node(N, L, 'MULTIPLY', lines, side), zr)
    base = N.new('ShaderNodeMix'); base.data_type = 'RGBA'
    base.inputs[6].default_value = (0.40, 0.07, 0.025, 1); base.inputs[7].default_value = (0.045, 0.045, 0.048, 1)
    L.new(stripe, base.inputs['Factor'])
    col = N.new('ShaderNodeMix'); col.data_type = 'RGBA'; col.inputs[7].default_value = (0.0, 0.0, 0.0, 1)
    L.new(gap, col.inputs['Factor']); L.new(base.outputs[2], col.inputs[6])
    L.new(col.outputs[2], p.inputs['Base Color'])
    dark = math_node(N, L, 'MAXIMUM', stripe, gap)
    for inp, a, b in (('Roughness', 0.30, 0.6), ('Metallic', 0.5, 0.0), ('Coat Weight', 1.0, 0.2)):
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
    (-2.250, 0.860, 0.770, 0.22, 0.700, 0.745, 0.0),
    (-2.215, 0.915, 0.855, 0.16, 0.745, 0.790, 0.0),
    (-2.100, 0.935, 0.950, 0.13, 0.790, 0.835, 0.0),
    (-1.850, 0.935, 1.035, 0.13, 0.835, 0.880, 0.0),
    (-1.525, 0.950, 1.070, 0.13, 0.870, 0.915, 0.0),
    (-1.200, 0.958, 1.050, 0.15, 0.890, 0.940, 0.0),
    (-0.920, 0.962, 0.985, 0.18, 0.900, 0.955, 0.012),
    (-0.400, 0.963, 0.980, 0.19, 0.912, 0.972, 0.050),
    (0.400, 0.965, 0.980, 0.19, 0.932, 0.992, 0.055),
    (0.980, 0.970, 0.990, 0.18, 0.952, 1.015, 0.022),
    (1.230, 0.975, 1.035, 0.165, 0.968, 1.035, 0.0),
    (1.525, 0.980, 1.070, 0.155, 0.982, 1.052, 0.0),
    (1.850, 0.975, 1.045, 0.16, 0.992, 1.068, 0.0),
    (2.200, 0.950, 0.990, 0.18, 0.998, 1.082, 0.0),
    (2.340, 0.915, 0.945, 0.19, 0.975, 1.060, 0.0),
    (2.395, 0.820, 0.840, 0.26, 0.935, 1.000, 0.0),
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


BUMPER_PUSH = 0.075


def push(x, z):
    wgt = min(1.0, max(0.0, (-2.08 - x) / 0.17))       # only the front-most stations
    lower = _sstep(0.60, 0.46, z)                      # 1 below z=0.50 (bumper), 0 above 0.66 (light band)
    wr = min(1.0, max(0.0, (x - 2.28) / 0.13))
    lower_r = _sstep(0.70, 0.58, z)
    return x - BUMPER_PUSH * wgt * lower + 0.055 * wr * lower_r


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
for i in range(len(rings) - 1):
    for col in (left_sh, right_sh):
        crease_pairs.append(tuple(sorted((i * n + col, (i + 1) * n + col))))
body = mesh_from('Body', verts, faces, PAINT, crease_pairs)
sub = body.modifiers.new('Sub', 'SUBSURF'); sub.levels = 2; sub.render_levels = 2

# wheel arches (widebody): one cutter per wheel, so each well has an inner wall
TIRE_F = wheels.tire_size(305, 35, 21)
TIRE_R = wheels.tire_size(305, 35, 21)
TRACK_Y = 0.900
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

from mathutils import Matrix
from mathutils.bvhtree import BVHTree
BVH = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
# widebody flare lips: body-colour rims around each arch, so the flare outline reads from the side
for ax, (r, w) in ((AXLE_F, TIRE_F), (AXLE_R, TIRE_R)):
    for s in (-1, 1):
        bpy.ops.mesh.primitive_torus_add(major_radius=r + 0.075, minor_radius=0.032, major_segments=128, minor_segments=14,
                                         location=(ax, s * 1.035, r + 0.015), rotation=(math.pi / 2, 0, 0))
        lip = bpy.context.active_object; lip.name = 'FlareLip%+d_%d' % (s, int(ax * 10))
        for cc in lip.users_collection: cc.objects.unlink(lip)
        car.objects.link(lip)
        mw = lip.matrix_world.copy()
        bm = bmesh.new(); bm.from_mesh(lip.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if (mw @ v.co).z < 0.26], context='VERTS')
        bm.to_mesh(lip.data); bm.free()
        lip.data.polygons.foreach_set('use_smooth', [True] * len(lip.data.polygons))
        lip.data.transform(mw); lip.matrix_world = Matrix.Identity(4)
        R = r + 0.075; z0 = r + 0.015; y0 = s * 1.035
        for v in lip.data.vertices:
            th = math.atan2(v.co.z - z0, v.co.x - ax)
            cx, cz = ax + R * math.cos(th), z0 + R * math.sin(th)
            hit = BVH.ray_cast(Vector((cx, s * 2.0, cz)), Vector((0, -s, 0)))
            surf = hit[0].y if hit[0] is not None and abs(hit[0].y) > 0.85 else y0
            v.co.y = surf + s * 0.006 + (v.co.y - y0) * 0.5     # flattened tube sitting on the surface
        lip.data.materials.append(PAINT)

# ---------------------------------------------------------------- greenhouse (traced from the photo)
# x, bottom half-width, top half-width, bottom z (beltline), top z (roof)
GH = [
    (-0.840, 0.875, 0.860, 0.968, 0.972),
    (-0.360, 0.865, 0.680, 0.982, 1.365),
    (0.000, 0.865, 0.700, 0.990, 1.400),
    (0.450, 0.870, 0.705, 1.000, 1.410),
    (0.950, 0.880, 0.700, 1.018, 1.395),
    (1.150, 0.886, 0.689, 1.031, 1.361),   # rear end of the side window (user's blue line)
    (1.300, 0.890, 0.680, 1.040, 1.335),
    (1.580, 0.895, 0.650, 1.055, 1.235),
    (1.800, 0.900, 0.620, 1.068, 1.150),
    (2.000, 0.900, 0.600, 1.078, 1.095),
]


def gh_interp(x):
    for k in range(len(GH) - 1):
        if GH[k][0] <= x <= GH[k + 1][0]:
            t = (x - GH[k][0]) / (GH[k + 1][0] - GH[k][0])
            return tuple(GH[k][q] + t * (GH[k + 1][q] - GH[k][q]) for q in range(5))
    return GH[-1]


# finer stations around the rear end of the side window so its curved edge comes out smooth
xs = sorted(set([g[0] for g in GH] + [round(0.85 + 0.025 * k, 3) for k in range(15)]))
GHF = [gh_interp(x) for x in xs]

WIN_TOP = 0.62                                   # window top = user's blue line (fraction of greenhouse height)
FR = [0.0, 0.08, 0.16, 0.24, 0.32, 0.40, 0.48, 0.55, WIN_TOP]


def _g(f):                                       # how far the side has leaned in (0 = beltline width, 1 = roof width)
    pts = [(0.0, 0.0), (0.35, 0.40), (0.62, 0.72), (0.93, 1.0)]
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
    paint.inputs['Base Color'].default_value = (0.40, 0.07, 0.025, 1); paint.inputs['Metallic'].default_value = 0.5
    paint.inputs['Roughness'].default_value = 0.30; paint.inputs['Coat Weight'].default_value = 1.0
    paint.inputs['Coat Roughness'].default_value = 0.03
    glass = N.new('ShaderNodeBsdfPrincipled')
    glass.inputs['Base Color'].default_value = (0.015, 0.018, 0.02, 1); glass.inputs['Roughness'].default_value = 0.02
    glass.inputs['Coat Weight'].default_value = 1.0
    tc = N.new('ShaderNodeTexCoord'); sp = N.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Object'], sp.inputs[0])
    X, Z = sp.outputs['X'], sp.outputs['Z']
    # greenhouse bottom/top heights near the rear door window (linear fit of the stations 0.95..1.30)
    zb = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', math_node(N, L, 'SUBTRACT', X, 0.95), 0.0629), 1.018)
    zt = math_node(N, L, 'SUBTRACT', 1.395, math_node(N, L, 'MULTIPLY', math_node(N, L, 'SUBTRACT', X, 0.95), 0.1714))
    hf = math_node(N, L, 'DIVIDE', math_node(N, L, 'SUBTRACT', Z, zb), math_node(N, L, 'SUBTRACT', zt, zb))
    t = math_node(N, L, 'DIVIDE', hf, WIN_TOP, clamp=True)
    edge = math_node(N, L, 'ADD', 1.01, math_node(N, L, 'MULTIPLY', 0.14,
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
    return 1.01 + 0.14 * math.sqrt(max(0.0, 1.0 - t * t))


for fi, f in enumerate(me.polygons):
    i, j = divmod(fi, gn - 1)
    xc = 0.5 * (GHF[i][0] + GHF[i + 1][0])
    if i == 0:                                   # windshield + A-pillar area: dark (user's yellow)
        f.material_index = GLASS_I
        continue
    if j < NROW or j > RAIL_R:                   # side-window rows
        r = j if j < NROW else (gn - 2 - j)
        t = 0.5 * (FR[r] + FR[r + 1]) / WIN_TOP
        if 0.93 <= xc <= 1.20:
            f.material_index = EDGE_I                # smooth curved edge drawn in the shader
        else:
            f.material_index = GLASS_I if xc < x_rear(t) else PAINT_I
    elif j in (RAIL_L, RAIL_R):                  # band above the windows (user's red)
        f.material_index = PAINT_I
    else:                                        # roof centre: body colour, rear window behind the cabin
        f.material_index = PAINT_I if xc < 1.15 else GLASS_I
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
    box('Belt%+d' % s, (2.30, 0.012, 0.018), (0.38, s * 0.874, 0.995), CHROME)
    box('BPillar%+d' % s, (0.065, 0.02, 0.24), (0.36, s * 0.84, 1.12), BLACK, rot=(s * math.radians(14), 0, 0))

# ---------------------------------------------------------------- front
FX = FRONT_X


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


MESH = honeycomb('Honeycomb')
# Front layout traced from the user's head-on photo (car width 2.03 m -> 0.00345 m/px, ground y=445 px).
# upper band: wide slim headlights at the outer ends, honeycomb grille between them (z 0.63-0.79)
box('Grille', (0.12, 1.08, 0.12), (FX + 0.03, 0, 0.665), MESH, bevel=0.02)
box('GrilleSurround', (0.12, 1.12, 0.014), (FX + 0.025, 0, 0.735), BLACK, bevel=0.005)
# thin secondary slot under the grille
box('UpperSlot', (0.12, 0.70, 0.04), (FX - 0.01, 0, 0.565), MESH, bevel=0.018)
for s in (-1, 1):
    # headlight: dark smoked lens, LED "C" ring (top, bottom, outer edge), inner projector
    # headlight kept on the flat part of the face (ends before the corner starts curving back)
    box('HeadLens%+d' % s, (0.12, 0.27, 0.11), (FX + 0.04, s * 0.695, 0.665), HEADLENS, rot=(s * math.radians(5), 0, 0), bevel=0.035)
    box('LEDTop%+d' % s, (0.03, 0.24, 0.010), (FX - 0.018, s * 0.70, 0.71), HEAD, rot=(s * math.radians(5), 0, 0))
    box('LEDBot%+d' % s, (0.03, 0.24, 0.010), (FX - 0.018, s * 0.70, 0.622), HEAD, rot=(s * math.radians(5), 0, 0))
    box('LEDOut%+d' % s, (0.03, 0.010, 0.09), (FX + 0.0, s * 0.825, 0.668), HEAD)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.035, depth=0.04, location=(FX - 0.03, s * 0.66, 0.71), rotation=(0, math.pi / 2, 0))
    pj = bpy.context.active_object; pj.name = 'Projector%+d' % s
    for cc in pj.users_collection: cc.objects.unlink(pj)
    car.objects.link(pj); pj.data.materials.append(CHROME)
    box('ProjInner%+d' % s, (0.01, 0.03, 0.03), (FX - 0.052, s * 0.66, 0.71), HEAD)
    # side intakes: black recess with two horizontal fins
    box('SideIntake%+d' % s, (0.12, 0.20, 0.20), (FX - 0.035, s * 0.655, 0.34), MESH, bevel=0.055)
    for zf in (0.30, 0.38):
        box('SideFin%+d_%d' % (s, int(zf * 100)), (0.05, 0.17, 0.018), (FX - 0.085, s * 0.655, zf), BLACK, bevel=0.006)
# big central lower intake (rounded rectangle, honeycomb)
box('LowerIntake', (0.12, 0.88, 0.22), (FX - 0.035, 0, 0.335), MESH, bevel=0.075)
# splitter lip
box('Splitter', (0.32, 1.62, 0.03), (FX + 0.02, 0, 0.17), SATIN, bevel=0.012)
# hood: domed power bulge with a forward-facing scoop slot near the windshield
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=(-1.20, 0, 0.912))
hb = bpy.context.active_object; hb.name = 'HoodBulge'; hb.scale = (0.68, 0.40, 0.065)
for cc in hb.users_collection: cc.objects.unlink(hb)
car.objects.link(hb); hb.data.materials.append(PAINT); bpy.ops.object.shade_smooth()
box('HoodScoop', (0.05, 0.36, 0.03), (-1.00, 0, 0.962), MESH, rot=(0, math.radians(-8), 0), bevel=0.012)

# ---------------------------------------------------------------- sides
for s in (-1, 1):
    box('Mirror%+d' % s, (0.13, 0.085, 0.075), (-0.55, s * 0.965, 1.055), PAINT, bevel=0.034)
    box('MirrorArm%+d' % s, (0.06, 0.07, 0.03), (-0.56, s * 0.90, 1.015), PAINT, bevel=0.01)
    for hx in (-0.10, 1.05):
        box('Handle%+d_%d' % (s, int(hx * 10)), (0.16, 0.012, 0.024), (hx, s * 0.972, 0.86), PAINT, bevel=0.008)
    box('Skirt%+d' % s, (2.15, 0.05, 0.07), (0.0, s * 0.975, 0.21), PAINT, bevel=0.02)
    box('FrontMarker%+d' % s, (0.10, 0.012, 0.022), (FX + 0.26, s * 0.925, 0.62), principled('Amber%+d' % s, (0.8, 0.35, 0.0), emit=(1, 0.45, 0), emit_strength=3))

# ---------------------------------------------------------------- rear
RX = REAR_X
PLATEM = principled('PlateWhite', (0.85, 0.86, 0.88), rough=0.35)
REVERSE = principled('ReverseLens', (0.55, 0.57, 0.6), rough=0.05, coat=1.0, emit=(1, 1, 1), emit_strength=0.4)
# Layout traced from the user's rear photo (car width 2.03 m -> 0.00312 m/px, ground y=480 px).
# wide ducktail spoiler across the deck edge, trailing edge kicked up
box('Spoiler', (0.16, 1.52, 0.05), (RX - 0.12, 0, 1.085), PAINT, rot=(0, math.radians(-18), 0), bevel=0.022)
for s_ in (-1, 1):
    box('SpoilerEnd%+d' % s_, (0.14, 0.03, 0.07), (RX - 0.12, s_ * 0.75, 1.10), PAINT, rot=(0, math.radians(-16), 0), bevel=0.012)
# full-width tail-light band: dark smoked lens with a red LED "racetrack" ring
box('TailLens', (0.08, 1.74, 0.19), (RX + 0.0, 0, 0.862), TAILLENS, bevel=0.04)
box('RingTop', (0.02, 1.64, 0.014), (RX + 0.043, 0, 0.940), TAIL)
box('RingLowMid', (0.02, 0.74, 0.014), (RX + 0.043, 0, 0.832), TAIL)
for s_ in (-1, 1):
    # lower bar steps down from the centre to the outer pods
    box('RingLowSlope%+d' % s_, (0.02, 0.26, 0.014), (RX + 0.043, s_ * 0.50, 0.805), TAIL, rot=(s_ * math.radians(-11), 0, 0))
    box('RingLowOut%+d' % s_, (0.02, 0.20, 0.014), (RX + 0.043, s_ * 0.73, 0.778), TAIL)
    box('RingEnd%+d' % s_, (0.02, 0.020, 0.16), (RX + 0.043, s_ * 0.83, 0.86), TAIL)
    # clear reverse-light pods inside the ring at each end
    box('Reverse%+d' % s_, (0.02, 0.24, 0.045), (RX + 0.041, s_ * 0.64, 0.892), REVERSE, bevel=0.012)
# recessed trunk-lid panel below the lights (body colour, bevelled edge reads as the lid outline)
box('TrunkPanel', (0.02, 1.20, 0.09), (RX + 0.02, 0, 0.71), PAINT, bevel=0.01)
# sculpted bumper: plate recess with a blank plate
box('PlateRecess', (0.05, 0.58, 0.26), (RX + 0.05, 0, 0.46), SATIN, bevel=0.035)
box('Plate', (0.012, 0.305, 0.152), (RX + 0.078, 0, 0.47), PLATEM, bevel=0.006)
for s_ in (-1, 1):
    box('BumperSlot%+d' % s_, (0.04, 0.025, 0.15), (RX + 0.03, s_ * 0.80, 0.45), GRILLE, bevel=0.008)
# black diffuser under the bumper with a centre hump, and two large round exhausts
box('Diffuser', (0.30, 1.56, 0.17), (RX - 0.06, 0, 0.19), SATIN, bevel=0.05)
box('DiffuserHump', (0.26, 0.62, 0.09), (RX - 0.04, 0, 0.27), SATIN, bevel=0.04)
for k, yy in enumerate((-0.30, -0.15, 0.0, 0.15, 0.30)):
    box('DiffFin%d' % k, (0.22, 0.012, 0.10), (RX - 0.02, yy, 0.16), GRILLE)
for s_ in (-1, 1):
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.075, depth=0.26, location=(RX + 0.0, s_ * 0.56, 0.24), rotation=(0, math.pi / 2, 0))
    ex = bpy.context.active_object; ex.name = 'Exhaust%+d' % s_
    for cc in ex.users_collection: cc.objects.unlink(ex)
    car.objects.link(ex); ex.data.materials.append(principled('TipMetal', (0.6, 0.6, 0.62), rough=0.3, metal=1.0))
    ex.modifiers.new('Tube', 'SOLIDIFY').thickness = 0.01
    ex.data.polygons.foreach_set('use_smooth', [True] * len(ex.data.polygons))
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.063, depth=0.01, location=(RX + 0.06, s_ * 0.56, 0.24), rotation=(0, math.pi / 2, 0))
    ei = bpy.context.active_object; ei.name = 'ExhaustInner%+d' % s_
    for cc in ei.users_collection: cc.objects.unlink(ei)
    car.objects.link(ei); ei.data.materials.append(GRILLE)

# ---------------------------------------------------------------- wheels: gloss black spokes, red calipers, no logos
wcol = bpy.data.collections.new('Wheels'); car.children.link(wcol)
wheels.ensure_materials()
for mname, colr, metal in (('WHL_Caliper', (0.6, 0.01, 0.01), 0.0), ('WHL_LogoGold', (0.02, 0.02, 0.02), 0.0)):
    mt = bpy.data.materials.get(mname)
    if mt and mt.use_nodes:
        for nd in mt.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED':
                nd.inputs['Base Color'].default_value = (*colr, 1); nd.inputs['Metallic'].default_value = metal
for tag, ax, (r, w), front in (('F', AXLE_F, TIRE_F, True), ('R', AXLE_R, TIRE_R, False)):
    for s, side in ((-1, 'L'), (1, 'R')):
        wheels.build_wheel(tag + side, (ax, s * TRACK_Y, r), r, w, 21, is_left=(s < 0), is_front=front,
                           collection=wcol, spin=math.radians(10 if front else -22))

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
    'corner':  ((-4.2, -2.6, 1.05), (-2.15, -0.75, 0.72), 50),
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
bpy.ops.wm.save_as_mainfile(filepath=OUT + '/muscle_sedan.blend')
print('saved blend')
names = list(CAMS) if 'all' in args else [a for a in args if a in CAMS]
for nm in names:
    sc.camera = cams[nm]
    sc.render.filepath = OUT + '/sedan_%s.png' % nm
    bpy.ops.render.render(write_still=True)
    print('rendered', nm)
