"""Export a lightweight, game-ready GLB of the muscle sedan (for web / mobile).
- removes the studio, cameras, lights and boolean cutters
- bakes the shader-only details into real geometry/material slots (hood stripe, curved rear-window edge)
- swaps every node material for a plain glTF-friendly PBR material
- lowers subdivision on the body and decimates the very dense wheels
usage: python3 export_game_glb.py <in.blend> <out.glb>
"""
import bpy, bmesh, sys, math

src, dst = sys.argv[1], sys.argv[2]
bpy.ops.wm.open_mainfile(filepath=src)
sc = bpy.context.scene

# ---------------------------------------------------------------- strip everything that is not the car
def strip_non_car():
    for o in list(bpy.data.objects):
        in_car = any(c.name in ('Car', 'Wheels') for c in o.users_collection)
        if not in_car or o.type in ('CAMERA', 'LIGHT') or o.name.startswith('ArchCut'):
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name not in ('Car', 'Wheels'):
            bpy.data.collections.remove(c)

# ---------------------------------------------------------------- simple glTF materials
def pbr(name, color, metal=0.0, rough=0.5, coat=0.0, emit=None, emit_strength=0.0, alpha=1.0):
    m = bpy.data.materials.get('G_' + name) or bpy.data.materials.new('G_' + name)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.03
    if emit:
        p.inputs['Emission Color'].default_value = (*emit, 1)
        p.inputs['Emission Strength'].default_value = emit_strength
    return m


PAINT = pbr('Paint', (0.40, 0.07, 0.025), metal=0.5, rough=0.3, coat=1.0)
STRIPE = pbr('Stripe', (0.045, 0.045, 0.048), rough=0.6)
GLASS = pbr('Glass', (0.015, 0.018, 0.02), rough=0.03, coat=1.0)
FALLBACK = {   # for node materials whose colour comes from a texture/node network
    'Paint': PAINT, 'WindowEdge': PAINT, 'Honeycomb': pbr('Mesh', (0.01, 0.01, 0.01), rough=0.7),
    'WHL_Rubber': pbr('Tyre', (0.025, 0.025, 0.027), rough=0.85),
    'WHL_RimGlossBlack': pbr('Rim', (0.02, 0.02, 0.022), metal=0.6, rough=0.2, coat=1.0),
    'WHL_SatinBlack': pbr('Satin', (0.02, 0.02, 0.02), rough=0.55),
    'WHL_BrakeDisc': pbr('Disc', (0.3, 0.3, 0.31), metal=0.8, rough=0.45),
    'WHL_Caliper': pbr('Caliper', (0.6, 0.01, 0.01), rough=0.35, coat=0.6),
    'WHL_LugMetal': pbr('Lug', (0.7, 0.7, 0.72), metal=1.0, rough=0.25),
    'WHL_LogoGold': pbr('Cap', (0.02, 0.02, 0.02), rough=0.4),
    'WHL_HubMetal': pbr('Hub', (0.4, 0.4, 0.42), metal=1.0, rough=0.35),
}


def simplify(m):
    if m is None or m.name.startswith('G_'):
        return m
    for key, rep in FALLBACK.items():
        if m.name.startswith(key):
            return rep
    p = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m.use_nodes else None
    if p is None:
        return pbr(m.name, (0.05, 0.05, 0.05))
    g = lambda k: p.inputs[k].default_value
    em = tuple(g('Emission Color')[:3]); es = g('Emission Strength')
    return pbr(m.name, tuple(g('Base Color')[:3]), metal=g('Metallic'), rough=g('Roughness'),
               coat=g('Coat Weight'), emit=em if es > 0 else None, emit_strength=es)


# ---------------------------------------------------------------- lighter geometry, modifiers applied
body = bpy.data.objects['Body']
body.modifiers['Sub'].levels = 2
gh = bpy.data.objects['Greenhouse']
gh.modifiers['Sub'].levels = 1
for o in bpy.data.objects:
    if o.type == 'MESH' and (o.name.endswith(('_tire', '_spokes', '_face', '_disc', '_rim', '_barrel', '_lettering'))
                             or '_tire' in o.name or '_spoke' in o.name):
        d = o.modifiers.new('Dec', 'DECIMATE'); d.ratio = 0.02

bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
car_meshes = [o for o in bpy.data.objects if o.type == 'MESH' and any(c.name in ('Car', 'Wheels') for c in o.users_collection)]
for o in car_meshes:
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dg)
    o.modifiers.clear()
    old = o.data; o.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    for i, slot in enumerate(o.material_slots):
        o.material_slots[i].material = simplify(slot.material)

strip_non_car()

# ---------------------------------------------------------------- hood stripe -> its own material slot
body = bpy.data.objects['Body']
body.data.materials.append(STRIPE); si = len(body.data.materials) - 1
for f in body.data.polygons:
    c = f.center
    if abs(c.y) < 0.33 and c.x < -0.85 and f.normal.z > 0.6:
        f.material_index = si

# ---------------------------------------------------------------- curved rear window edge -> real geometry
gh = bpy.data.objects['Greenhouse']
mats = [s.material for s in gh.material_slots]
gi = mats.index(GLASS) if GLASS in mats else None
if gi is None:
    gh.data.materials.append(GLASS); gi = len(gh.data.materials) - 1
pi = mats.index(PAINT) if PAINT in mats else None
if pi is None:
    gh.data.materials.append(PAINT); pi = len(gh.data.materials) - 1


def edge_x(x, z):
    zb = 1.018 + (x - 0.95) * 0.0629
    zt = 1.395 - (x - 0.95) * 0.1714
    t = min(1.0, max(0.0, (z - zb) / (zt - zb) / 0.62))
    return 1.01 + 0.14 * math.sqrt(max(0.0, 1.0 - t * t))


bm = bmesh.new(); bm.from_mesh(gh.data)
zone = [f for f in bm.faces if 0.92 <= f.calc_center_median().x <= 1.20 and abs(f.normal.y) > 0.3 and 0.98 < f.calc_center_median().z < 1.33]
edges = list({e for f in zone for e in f.edges})
bmesh.ops.subdivide_edges(bm, edges=edges, cuts=2, use_grid_fill=True)
for f in bm.faces:
    c = f.calc_center_median()
    if 0.90 <= c.x <= 1.25 and abs(f.normal.y) > 0.3 and 0.98 < c.z < 1.40:
        f.material_index = pi if c.x > edge_x(c.x, c.z) else gi
bm.to_mesh(gh.data); bm.free()

# ---------------------------------------------------------------- export
tris = sum(len(p.vertices) - 2 for o in bpy.data.objects if o.type == 'MESH' for p in o.data.polygons)
print('triangles:', tris)
for o in sorted([o for o in bpy.data.objects if o.type == 'MESH'], key=lambda o: -len(o.data.polygons))[:8]:
    print('  ', o.name, len(o.data.polygons))
kw = dict(filepath=dst, export_format='GLTF_EMBEDDED' if dst.endswith('.gltf') else 'GLB', export_apply=True, export_yup=True, use_selection=False)
try:
    bpy.ops.export_scene.gltf(**kw, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    print('exported with draco')
except Exception as e:
    print('draco failed, plain export:', e)
    bpy.ops.export_scene.gltf(**kw)
