"""Traffic generator: builds every AI traffic vehicle from one script and a short "card" of numbers per type.
Same conventions as the player cars: forward = -X, left = -Y, up = +Z, metres, wheels on the ground at z = 0.
usage:
  python3 traffic.py lineup                  -> renders all vehicles side by side (out/lineup.png)
  python3 traffic.py export                  -> one light .glb per vehicle type in out/ (for the game)
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector, Matrix

bpy.ops.wm.read_factory_settings(use_empty=True)
HERE = os.path.dirname(os.path.abspath(__file__))
LOW = len(sys.argv) > 1 and sys.argv[1] == 'export'     # lighter meshes for the game
OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)

# ===================================================================== the cards
# Lofted bodies: stations along the length (x, half-width, bottom z, beltline z, roof z, roof lean-in).
# Between stations the shape is interpolated, so a card only needs the key points of the side profile.
# windows: side = list of (x_from, x_to); screen = windscreen x-range; rear = rear-window x-range (or None)
CARDS = {
    'hatchback': dict(
        name='Hatchback', paint=(0.55, 0.02, 0.02),
        stations=[(-2.025, .80, .30, .62, .66, .02), (-1.95, .86, .22, .68, .72, .02), (-1.70, .88, .18, .74, .78, .02),
                  (-1.05, .89, .18, .86, .90, .03), (-0.50, .89, .18, .88, 1.40, .14), (0.60, .89, .18, .90, 1.46, .16),
                  (1.50, .89, .18, .92, 1.42, .15), (1.92, .87, .22, .92, 1.26, .12), (2.025, .80, .30, .86, 1.06, .08)],
        side=[(-0.45, 0.28), (0.36, 1.45)], screen=(-1.0, -0.45), rear=(1.55, 2.03),
        axles=[-1.22, 1.33], tyre=(0.31, 0.20), track=0.755, rim=(0.75, 0.76, 0.78)),
    'saloon': dict(
        name='Saloon', paint=(0.52, 0.53, 0.55),
        stations=[(-2.35, .80, .30, .62, .66, .02), (-2.25, .88, .22, .68, .72, .02), (-1.95, .90, .18, .74, .78, .02),
                  (-1.00, .91, .18, .86, .90, .03), (-0.42, .91, .18, .88, 1.38, .15), (0.55, .91, .18, .90, 1.44, .17),
                  (1.05, .91, .18, .92, 1.38, .16), (1.58, .91, .18, .94, 1.02, .06), (2.25, .89, .22, .95, 1.00, .04),
                  (2.35, .82, .30, .90, .95, .03)],
        side=[(-0.38, 0.42), (0.50, 1.20)], screen=(-1.0, -0.42), rear=(1.05, 1.60),
        axles=[-1.40, 1.40], tyre=(0.32, 0.21), track=0.775, rim=(0.06, 0.06, 0.065)),
    'estate': dict(
        name='Estate', paint=(0.02, 0.17, 0.06),
        stations=[(-2.40, .80, .30, .62, .66, .02), (-2.30, .88, .22, .68, .72, .02), (-2.00, .90, .18, .74, .78, .02),
                  (-1.05, .91, .18, .86, .90, .03), (-0.47, .91, .18, .88, 1.40, .15), (0.55, .91, .18, .90, 1.46, .17),
                  (1.70, .91, .18, .93, 1.44, .16), (2.25, .89, .22, .95, 1.38, .14), (2.40, .82, .30, .92, 1.20, .10)],
        side=[(-0.42, 0.42), (0.50, 1.32), (1.40, 2.15)], screen=(-1.05, -0.47), rear=(2.20, 2.40),
        axles=[-1.45, 1.42], tyre=(0.32, 0.21), track=0.775, rim=(0.75, 0.76, 0.78)),
    'suv': dict(
        name='SUV', paint=(0.02, 0.04, 0.24),
        stations=[(-2.325, .84, .42, .80, .84, .02), (-2.22, .92, .34, .88, .92, .02), (-1.90, .94, .30, .98, 1.02, .02),
                  (-1.05, .95, .30, 1.04, 1.08, .03), (-0.52, .95, .30, 1.06, 1.66, .12), (0.60, .95, .30, 1.08, 1.72, .13),
                  (1.95, .95, .30, 1.10, 1.70, .12), (2.24, .93, .34, 1.10, 1.62, .10), (2.325, .86, .40, 1.05, 1.45, .08)],
        side=[(-0.47, 0.40), (0.48, 1.35), (1.43, 2.10)], screen=(-1.05, -0.52), rear=(2.15, 2.33),
        axles=[-1.38, 1.40], tyre=(0.37, 0.24), track=0.815, rim=(0.75, 0.76, 0.78), clearance=True),
    'van': dict(
        name='Van', paint=(0.80, 0.80, 0.80),
        stations=[(-2.75, .90, .42, .80, .84, .02), (-2.65, .98, .36, .86, .92, .02), (-2.35, 1.00, .34, 1.00, 1.06, .03),
                  (-1.95, 1.01, .34, 1.10, 1.20, .03), (-1.45, 1.01, .34, 1.12, 2.38, .06), (-1.00, 1.02, .34, 1.12, 2.48, .06),
                  (2.60, 1.02, .34, 1.12, 2.48, .06), (2.75, .98, .40, 1.10, 2.40, .06)],
        side=[(-1.40, -0.72)], screen=(-1.95, -1.42), rear=None,
        axles=[-1.75, 1.75], tyre=(0.36, 0.22), track=0.86, rim=(0.6, 0.6, 0.62)),
    # cab-only loft + a separate box body
    'boxvan': dict(
        name='Box van', paint=(0.70, 0.46, 0.02), box_colour=(0.85, 0.85, 0.86),
        stations=[(-3.30, .90, .42, .80, .84, .02), (-3.20, .98, .36, .86, .92, .02), (-2.90, 1.00, .34, 1.00, 1.06, .03),
                  (-2.50, 1.01, .34, 1.10, 1.20, .03), (-2.00, 1.01, .34, 1.12, 2.25, .06), (-1.05, 1.02, .34, 1.12, 2.30, .06),
                  (-0.95, .98, .40, 1.10, 2.20, .06)],
        side=[(-1.95, -1.22)], screen=(-2.50, -2.02), rear=None,
        box=(-1.10, 3.30, 0.58, 3.25, 1.10),          # x from, x to, z bottom, z top, half-width
        axles=[-2.25, 1.60], tyre=(0.37, 0.22), track=0.88, rim=(0.6, 0.6, 0.62)),
}
# boxy heavy vehicles are made from rounded boxes
HEAVY = {
    'lorry': dict(name='Lorry', paint=(0.75, 0.16, 0.01), trailer=(0.86, 0.86, 0.87),
                  axles=[(-7.30, 0.50, 0.32), (-4.40, 0.50, 0.32), (4.90, 0.45, 0.30), (6.20, 0.45, 0.30), (7.50, 0.45, 0.30)], track=0.92),
    'coach': dict(name='Coach', paint=(0.26, 0.05, 0.40), axles=[(-4.30, 0.52, 0.30), (3.00, 0.52, 0.30), (4.35, 0.52, 0.30)], track=0.95),
}

# ===================================================================== materials
def principled(name, color, rough=0.4, metal=0.0, coat=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.06
    if emit:
        p.inputs['Emission Color'].default_value = (*emit, 1)
        p.inputs['Emission Strength'].default_value = emit_strength
    return m


def paint(name, color):
    return principled(name, color, rough=0.38, metal=0.35, coat=0.8)


GLASS = principled('T_Glass', (0.015, 0.018, 0.022), rough=0.05, coat=1.0)
BLACK = principled('T_Black', (0.012, 0.012, 0.013), rough=0.5)
TRIM = principled('T_Trim', (0.02, 0.02, 0.022), rough=0.25, coat=0.4)
TYRE = principled('T_Tyre', (0.022, 0.022, 0.024), rough=0.85)
HEAD = principled('T_Head', (1, 1, 1), emit=(0.9, 0.95, 1.0), emit_strength=6)
TAIL = principled('T_Tail', (0.5, 0.0, 0.0), rough=0.2, emit=(1.0, 0.03, 0.02), emit_strength=3)
PLATE_F = principled('T_PlateF', (0.85, 0.86, 0.88), rough=0.35)
PLATE_R = principled('T_PlateR', (0.85, 0.66, 0.05), rough=0.35)
INDICATOR = principled('T_Amber', (0.8, 0.35, 0.0), emit=(1, 0.45, 0), emit_strength=1.5)
CHASSIS = principled('T_Chassis', (0.03, 0.03, 0.035), rough=0.7)


# ===================================================================== helpers
def link(o, coll):
    coll.objects.link(o); return o


def rbox(name, coll, size, loc, mat, bevel=0.04, rot=(0, 0, 0)):
    """rounded box (size baked into the mesh so bevels are true radii)"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
    me.transform(Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    o = bpy.data.objects.new(name, me); o.location = loc; o.rotation_euler = rot
    me.materials.append(mat); link(o, coll)
    if bevel:
        bv = o.modifiers.new('Bevel', 'BEVEL'); bv.width = bevel; bv.segments = 1 if LOW else 3
        me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
        o.modifiers.new('WN', 'WEIGHTED_NORMAL').keep_sharp = True
    return o


def interp_stations(st, step=None):
    step = step or (0.32 if LOW else 0.18)
    """dense stations by linear interpolation of the card's key stations"""
    out = []
    for a, b in zip(st, st[1:]):
        n = max(1, int(round((b[0] - a[0]) / step)))
        for k in range(n):
            t = k / n
            out.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(6)))
    out.append(st[-1])
    return out


def section(w, zb, zbelt, zroof, lean):
    """half cross-section from the bottom edge round to the roof centre"""
    h = max(zroof - zbelt, 0.0)
    return [
        (w - 0.10, zb), (w - 0.012, zb + 0.10), (w, zb + 0.32 * (zbelt - zb)), (w, zbelt - 0.06), (w - 0.01, zbelt),
        (w - lean * 0.5, zbelt + h * 0.55), (w - lean, zroof - 0.05 * (h > 0.1)), (w - lean - 0.10, zroof),
    ]


def loft_body(name, coll, stations, mat):
    st = interp_stations(stations)
    rings = []
    for x, w, zb, zbelt, zroof, lean in st:
        hs = section(w, zb, zbelt, zroof, lean)
        rings.append([(x, 0.0, zb)] + [(x, -y, z) for y, z in hs] + [(x, 0.0, zroof)] + [(x, y, z) for y, z in reversed(hs)])
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
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # crisp shoulder line along the beltline
    cl = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    for e in bm.edges:
        i0, i1 = e.verts[0].index, e.verts[1].index
        if i0 < last + n and i1 < last + n and i0 % n == i1 % n and (i0 % n) in (5, n - 5):
            e[cl] = 0.8
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); me.materials.append(mat); link(o, coll)
    o.modifiers.new('Sub', 'SUBSURF').levels = 1 if LOW else 2
    return o


def apply_all(o):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=False, depsgraph=dg)
    o.modifiers.clear(); old = o.data; o.data = me
    if old.users == 0: bpy.data.meshes.remove(old)


def assign_glass(o, card):
    """after subdivision: side windows, windscreen and rear window get glass, by position and facing"""
    me = o.data
    me.materials.append(GLASS); gi = len(me.materials) - 1
    st = card['stations']
    def belt_roof(x):
        for a, b in zip(st, st[1:]):
            if a[0] <= x <= b[0]:
                t = (x - a[0]) / (b[0] - a[0] + 1e-9)
                return a[3] + (b[3] - a[3]) * t, a[4] + (b[4] - a[4]) * t
        return st[-1][3], st[-1][4]
    def interp(x, i):
        if x <= st[0][0]: return st[0][i]
        for a, b in zip(st, st[1:]):
            if a[0] <= x <= b[0]:
                t = (x - a[0]) / (b[0] - a[0] + 1e-9)
                return a[i] + (b[i] - a[i]) * t
        return st[-1][i]
    # slice the body along every window edge first, so each window is bounded by real edges
    # (picking whole faces on the plain subdivided mesh gave saw-tooth edges and blotches)
    bm = bmesh.new(); bm.from_mesh(me)
    def cut(co, no):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=co, plane_no=no)
    for a, b in card['side']:
        cut((a, 0, 0), (1, 0, 0)); cut((b, 0, 0), (1, 0, 0))
        za, zb_ = belt_roof(a)[0] + 0.035, belt_roof(b)[0] + 0.035
        cut((a, 0, za), Vector((-(zb_ - za) / (b - a), 0, 1)).normalized())
    s0, s1 = card['screen']
    ys = interp(s1, 1) - interp(s1, 5) - 0.10
    cut((0, ys, 0), (0, 1, 0)); cut((0, -ys, 0), (0, 1, 0))
    cut((s0, 0, 0), (1, 0, 0))
    yr = zr = None
    if card['rear']:
        r0, r1 = card['rear']
        yr = min(interp(x, 1) - interp(x, 5) for x in (r0, (r0 + r1) / 2, r1)) - 0.12
        zr = belt_roof(r1)[0] + 0.07
        cut((r0, 0, 0), (1, 0, 0)); cut((0, 0, zr), (0, 0, 1))
        cut((0, yr, 0), (0, 1, 0)); cut((0, -yr, 0), (0, 1, 0))
    bm.to_mesh(me); bm.free()
    for f in me.polygons:
        c, nrm = f.center, f.normal
        zbelt, zroof = belt_roof(c.x)
        if c.z < zbelt + 0.035:
            continue
        if abs(nrm.y) > 0.45 and c.z < zroof - 0.06:
            if any(a <= c.x <= b for a, b in card['side']):
                f.material_index = gi
        elif nrm.x < -0.18 and s0 <= c.x <= s1 and abs(c.y) < ys:            # the windscreen is the sloping roofline itself
            f.material_index = gi
        elif yr and nrm.x > 0.12 and c.x >= card['rear'][0] and c.z > zr and abs(c.y) < yr and c.z < zroof - 0.03:
            f.material_index = gi


def smooth_hard_edges(o, angle=38):
    bm = bmesh.new(); bm.from_mesh(o.data)
    for f in bm.faces: f.smooth = True
    hard = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(angle)]
    bmesh.ops.split_edges(bm, edges=hard)
    bm.to_mesh(o.data); bm.free()


def surface_x(objs, y, z, front):
    """x of the outermost real surface at (y, z), seen from the front (-x) or the back (+x)"""
    dg = bpy.context.evaluated_depsgraph_get()
    org = Vector((-60.0 if front else 60.0, y, z)); d = Vector((1, 0, 0)) if front else Vector((-1, 0, 0))
    best = None
    for o in objs:
        inv = o.matrix_world.inverted()
        ok, loc, _n, _i = o.ray_cast(inv @ org, (inv.to_3x3() @ d).normalized(), depsgraph=dg)
        if ok:
            x = (o.matrix_world @ loc).x
            best = x if best is None else (min(best, x) if front else max(best, x))
    return best


def snapped(name, coll, objs, size, y, z, front, mat, bevel):
    """a lamp / plate / grille box sitting on the actual (subdivided) surface: its face 1.2 cm proud of the
    outermost point under it and deep enough to reach back into the body, so it never hides or flickers"""
    hy, hz = size[1] / 2 * 0.9, size[2] / 2 * 0.9
    xs = [surface_x(objs, y + dy, z + dz, front) for dy, dz in ((0, 0), (hy, hz), (-hy, hz), (hy, -hz), (-hy, -hz))]
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    outer = min(xs) if front else max(xs); inner = max(xs) if front else min(xs)
    depth = max(size[0], abs(inner - outer) + 0.04)
    face = outer - 0.012 if front else outer + 0.012
    cx = face + depth / 2 if front else face - depth / 2
    return rbox(name, coll, (depth, size[1], size[2]), (cx, y, z), mat, bevel=bevel)


def simple_wheel(name, coll, x, y, r, w, rim_col, left):
    """light game wheel: rounded tyre, rim disc with five spokes and a hub; rim face points outward"""
    parts = []
    rimm = principled(name + '_rim', rim_col, rough=0.28, metal=0.9)
    side = -1 if left else 1
    bpy.ops.mesh.primitive_cylinder_add(vertices=24 if LOW else 40, radius=r, depth=w, location=(x, y, r), rotation=(math.pi / 2, 0, 0))
    t = bpy.context.active_object; t.name = name + '_tyre'
    for cc in t.users_collection: cc.objects.unlink(t)
    link(t, coll); t.data.materials.append(TYRE)
    bv = t.modifiers.new('B', 'BEVEL'); bv.width = min(0.06, w * 0.3); bv.segments = 2 if LOW else 4
    t.data.polygons.foreach_set('use_smooth', [True] * len(t.data.polygons))
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r * 0.66, depth=0.02, location=(x, y + side * (w / 2 - 0.005), r), rotation=(math.pi / 2, 0, 0))
    d = bpy.context.active_object; d.name = name + '_barrel'
    for cc in d.users_collection: cc.objects.unlink(d)
    link(d, coll); d.data.materials.append(BLACK)
    for k in range(5):
        a = k * 2 * math.pi / 5
        sp = rbox(name + '_spoke%d' % k, coll, (0.055 * r / 0.33, 0.02, r * 0.58), (x, y + side * (w / 2 + 0.004), r), rimm, bevel=0.006, rot=(0, a, 0))
        sp.location = (x + math.sin(a) * r * 0.30, y + side * (w / 2 + 0.004), r + math.cos(a) * r * 0.30)
    bpy.ops.mesh.primitive_torus_add(major_radius=r * 0.62, minor_radius=r * 0.045, major_segments=24 if LOW else 40, minor_segments=5 if LOW else 8,
                                     location=(x, y + side * (w / 2 + 0.004), r), rotation=(math.pi / 2, 0, 0))
    lip = bpy.context.active_object; lip.name = name + '_lip'
    for cc in lip.users_collection: cc.objects.unlink(lip)
    link(lip, coll); lip.data.materials.append(rimm)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=r * 0.13, depth=0.05, location=(x, y + side * (w / 2 + 0.01), r), rotation=(math.pi / 2, 0, 0))
    hub = bpy.context.active_object; hub.name = name + '_hub'
    for cc in hub.users_collection: cc.objects.unlink(hub)
    link(hub, coll); hub.data.materials.append(rimm)


def lights_and_plates(coll, x_front, x_rear, w, z_head, z_tail, z_plate_f, z_plate_r, light_w=0.30):
    """lamps and plates snapped onto whatever bodywork is already in the collection"""
    objs = [o for o in coll.objects if o.type == 'MESH']
    for s in (-1, 1):
        snapped('Head%+d' % s, coll, objs, (0.05, light_w, 0.08), s * (w - 0.12 - light_w / 2), z_head, True, HEAD, 0.015)
        snapped('Tail%+d' % s, coll, objs, (0.05, light_w * 0.9, 0.09), s * (w - 0.12 - light_w * 0.45), z_tail, False, TAIL, 0.015)
        snapped('IndF%+d' % s, coll, objs, (0.04, 0.06, 0.04), s * (w - 0.10), z_head - 0.07, True, INDICATOR, 0.008)
    snapped('PlateF', coll, objs, (0.02, 0.52, 0.11), 0, z_plate_f, True, PLATE_F, 0.004)
    snapped('PlateR', coll, objs, (0.02, 0.52, 0.11), 0, z_plate_r, False, PLATE_R, 0.004)


# ===================================================================== builders
def build_lofted(key, coll, colour=None):
    c = CARDS[key]; P = paint('Paint_' + key, colour or c['paint'])
    body = loft_body('Body_' + key, coll, c['stations'], P)
    apply_all(body)
    assign_glass(body, c)
    # wheel arches
    r, w = c['tyre']
    for ax in c['axles']:
        for s in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24 if LOW else 48, radius=r + 0.05, depth=0.6, location=(ax, s * (c['track'] + 0.25), r + 0.02), rotation=(math.pi / 2, 0, 0))
            cut = bpy.context.active_object
            bo = body.modifiers.new('Arch', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.object = cut; bo.solver = 'EXACT'
            apply_all(body)
            bpy.data.objects.remove(cut, do_unlink=True)
    xf, xr = c['stations'][0][0], c['stations'][-1][0]
    w0 = max(s_[1] for s_ in c['stations'])
    zb_f, zbelt_f = c['stations'][1][2], c['stations'][1][3]
    zb_r, zbelt_r = c['stations'][-2][2], c['stations'][-2][3]
    if 'box' in c:
        bx0, bx1, bz0, bz1, bw = c['box']
        rbox('Box_' + key, coll, (bx1 - bx0, bw * 2, bz1 - bz0), ((bx0 + bx1) / 2, 0, (bz0 + bz1) / 2), paint('Box_' + key, c['box_colour']), bevel=0.05)
        rbox('Underframe_' + key, coll, (bx1 - bx0 - 0.2, bw * 1.6, 0.20), ((bx0 + bx1) / 2, 0, bz0 - 0.08), CHASSIS, bevel=0.01)
        xr_ = bx1; zt_r = 0.85
    else:
        xr_ = xr; zt_r = zbelt_r - 0.10
    smooth_hard_edges(body)
    snapped('Grille_' + key, coll, [body], (0.05, w0 * 0.62, 0.11), 0, zb_f + 0.27, True, BLACK, 0.02)
    lights_and_plates(coll, xf + 0.04, xr_ - 0.03, w0, zbelt_f - 0.10, zt_r, zb_f + 0.13, zb_r + 0.30 if 'box' not in c else 0.50)
    for s in (-1, 1):   # mirrors
        xm = c['screen'][1] + 0.08
        rbox('Mirror%+d' % s, coll, (0.12, 0.10, 0.09), (xm, s * (w0 + 0.07), (c['stations'][4][3]) + 0.12), P, bevel=0.025)
    for ax in c['axles']:
        for s in (-1, 1):
            simple_wheel('W%+d_%d' % (s, int(ax * 10)), coll, ax, s * c['track'], r, w, c['rim'], left=s < 0)


def build_lorry(coll, colour=None):
    c = HEAVY['lorry']; P = paint('Paint_lorry', colour or c['paint']); TR = paint('Trailer', c['trailer'])
    # cab-over tractor unit
    rbox('Cab', coll, (2.30, 2.48, 2.55), (-7.10, 0, 0.55 + 1.275), P, bevel=0.10)
    rbox('Fairing', coll, (1.4, 2.40, 0.8), (-6.70, 0, 3.10 + 0.40), P, bevel=0.12, rot=(0, math.radians(-12), 0))
    rbox('Screen', coll, (0.04, 2.20, 0.95), (-8.26, 0, 2.30), GLASS, bevel=0.03, rot=(0, math.radians(-4), 0))
    for s in (-1, 1):
        rbox('CabWin%+d' % s, coll, (0.85, 0.03, 0.70), (-7.75, s * 1.245, 2.25), GLASS, bevel=0.02)
        rbox('Mirror%+d' % s, coll, (0.10, 0.12, 0.45), (-8.05, s * 1.36, 2.30), BLACK, bevel=0.02)
        rbox('Step%+d' % s, coll, (0.60, 0.12, 0.35), (-7.60, s * 1.20, 0.65), BLACK, bevel=0.02)
    rbox('Bumper', coll, (0.25, 2.50, 0.40), (-8.22, 0, 0.62), BLACK, bevel=0.04)
    rbox('Grille', coll, (0.05, 1.60, 0.55), (-8.24, 0, 1.15), TRIM, bevel=0.02)
    rbox('Chassis', coll, (12.0, 1.0, 0.30), (-2.0, 0, 0.70), CHASSIS, bevel=0.02)
    # trailer
    rbox('Trailer', coll, (13.6, 2.55, 2.75), (1.40, 0, 1.25 + 1.375), TR, bevel=0.05)
    for s in (-1, 1):
        rbox('Stripe%+d' % s, coll, (13.0, 0.02, 0.10), (1.40, s * 1.28, 1.45), P, bevel=0)
        rbox('Skirt%+d' % s, coll, (5.0, 0.04, 0.45), (0.80, s * 1.20, 0.95), BLACK, bevel=0.01)
    rbox('RearDoors', coll, (0.03, 2.40, 2.55), (8.21, 0, 2.62), TR, bevel=0.01)
    rbox('UnderRun', coll, (0.12, 2.30, 0.15), (8.10, 0, 0.55), BLACK, bevel=0.01)
    for s in (-1, 1):
        rbox('Head%+d' % s, coll, (0.05, 0.30, 0.15), (-8.30, s * 0.92, 0.95), HEAD, bevel=0.02)
        rbox('Tail%+d' % s, coll, (0.05, 0.25, 0.12), (8.23, s * 1.05, 0.95), TAIL, bevel=0.02)
    rbox('PlateR', coll, (0.02, 0.52, 0.11), (8.24, 0, 0.75), PLATE_R, bevel=0.004)
    for ax, r, w in c['axles']:
        for s in (-1, 1):
            simple_wheel('W%+d_%d' % (s, int(ax * 10)), coll, ax, s * c['track'], r, w, (0.7, 0.7, 0.72), left=s < 0)


def build_coach(coll, colour=None):
    c = HEAVY['coach']; P = paint('Paint_coach', colour or c['paint']); WHITE = paint('CoachWhite', (0.86, 0.86, 0.87))
    rbox('Body', coll, (12.2, 2.55, 3.15), (0, 0, 0.42 + 1.575), WHITE, bevel=0.18)
    rbox('Livery', coll, (12.24, 2.59, 0.95), (0, 0, 0.95), P, bevel=0.12)
    rbox('Screen', coll, (0.05, 2.35, 1.75), (-6.09, 0, 2.38), GLASS, bevel=0.06, rot=(0, math.radians(-6), 0))
    rbox('RearWin', coll, (0.04, 2.0, 0.9), (6.10, 0, 2.75), GLASS, bevel=0.04)
    for s in (-1, 1):
        rbox('WinBand%+d' % s, coll, (10.7, 0.03, 1.35), (0.40, s * 1.276, 2.55), GLASS, bevel=0.04)
        for k in range(8):                             # window pillars
            rbox('Pillar%+d_%d' % (s, k), coll, (0.09, 0.035, 1.36), (-4.40 + k * 1.40, s * 1.305, 2.55), BLACK, bevel=0)
        rbox('Mirror%+d' % s, coll, (0.10, 0.10, 0.40), (-6.30, s * 1.30, 2.70), BLACK, bevel=0.02)
        rbox('Bays%+d' % s, coll, (6.0, 0.02, 0.012), (0.2, s * 1.31, 1.45), BLACK, bevel=0)
    rbox('Door', coll, (1.05, 0.035, 2.3), (-5.25, 1.305, 1.75), GLASS, bevel=0.03)
    rbox('Bumper', coll, (0.20, 2.5, 0.35), (-6.12, 0, 0.55), BLACK, bevel=0.05)
    rbox('BumperR', coll, (0.20, 2.5, 0.35), (6.12, 0, 0.55), BLACK, bevel=0.05)
    lights_and_plates(coll, -6.14, 6.14, 1.275, 0.95, 1.05, 0.62, 0.75, light_w=0.36)
    for ax, r, w in c['axles']:
        for s in (-1, 1):
            simple_wheel('W%+d_%d' % (s, int(ax * 10)), coll, ax, s * c['track'], r, w, (0.7, 0.7, 0.72), left=s < 0)


def build(key, coll, colour=None):
    if key in CARDS: build_lofted(key, coll, colour)
    elif key == 'lorry': build_lorry(coll, colour)
    elif key == 'coach': build_coach(coll, colour)


ORDER = ['hatchback', 'saloon', 'estate', 'suv', 'van', 'boxvan', 'coach', 'lorry']


def vehicle_collection(key):
    coll = bpy.data.collections.new('veh_' + key); bpy.context.scene.collection.children.link(coll)
    return coll


def move_collection(coll, dx, dy, rz=0.0):
    M = Matrix.Translation((dx, dy, 0)) @ Matrix.Rotation(rz, 4, 'Z')
    for o in coll.objects:
        o.matrix_world = M @ o.matrix_world


# ===================================================================== main
sc = bpy.context.scene
mode = sys.argv[1] if len(sys.argv) > 1 else 'lineup'

if mode == 'lineup':
    # front row: cars and vans; back row: coach and lorry
    spots = {'hatchback': (-15.0, -2.5), 'saloon': (-9.6, -2.5), 'estate': (-4.0, -2.5), 'suv': (1.6, -2.5),
             'van': (7.6, -2.5), 'boxvan': (14.4, -2.5), 'coach': (-7.5, 4.6), 'lorry': (9.0, 4.6)}
    for key in ORDER:
        coll = vehicle_collection(key); build(key, coll)
        move_collection(coll, *spots[key])
    # simple outdoor-style light for a readable line-up
    sc.render.engine = 'CYCLES'; sc.cycles.samples = int(sys.argv[2]) if len(sys.argv) > 2 else 48; sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'AgX'
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1000
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.62, 0.70, 0.80, 1); bg.inputs[1].default_value = 0.9
    ld = bpy.data.lights.new('sun', 'SUN'); ld.energy = 3.2; ld.angle = math.radians(3)
    so = bpy.data.objects.new('sun', ld); sc.collection.objects.link(so); so.rotation_euler = (math.radians(48), math.radians(8), math.radians(-40))
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    fl = bpy.context.active_object; fl.data.materials.append(principled('Floor', (0.18, 0.19, 0.20), rough=0.6))
    cd = bpy.data.cameras.new('cam'); cd.lens = 30
    cam = bpy.data.objects.new('cam', cd); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (-17.0, -27.0, 13.5)
    cam.rotation_euler = (Vector((1.0, 1.5, 0.6)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'traffic_lineup.blend'))
    sc.render.filepath = os.path.join(OUT, 'lineup.png')
    bpy.ops.render.render(write_still=True)
    print('rendered lineup')

if mode == 'export':
    # one light model per vehicle type: modifiers applied, all parts joined into one mesh, glTF for the game
    import struct, json, base64
    gdir = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(gdir, exist_ok=True)
    report = {}
    for key in ORDER:
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for c_ in list(bpy.data.collections):
            bpy.data.collections.remove(c_)
        coll = vehicle_collection(key); build(key, coll)
        vl = bpy.context.view_layer
        objs = [o for o in coll.objects if o.type == 'MESH']
        for o in objs:
            apply_all(o)
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs: o.select_set(True)
        vl.objects.active = objs[0]
        bpy.ops.object.join()
        joined = vl.objects.active; joined.name = 'veh_' + key
        tris = sum(len(p.vertices) - 2 for p in joined.data.polygons)
        glb = os.path.join(OUT, key + '.glb')
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=True, export_yup=True)
        data = open(glb, 'rb').read(); off, js, binc = 12, None, None
        while off < len(data):
            clen, ctype = struct.unpack_from('<I4s', data, off); off += 8
            chunk = data[off:off + clen]; off += clen
            if ctype == b'JSON': js = json.loads(chunk)
            elif ctype == b'BIN\x00': binc = chunk
        js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(binc).decode()
        json.dump(js, open(os.path.join(gdir, key + '.json'), 'w'), separators=(',', ':'))
        report[key] = tris
        print('exported', key, tris, 'tris')
    print('REPORT', report)
