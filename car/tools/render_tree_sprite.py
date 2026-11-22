"""Render a Poly Haven plant model to transparent billboard sprites (two views, 90 deg apart)."""
import bpy, sys, math
from mathutils import Vector
src, out, res = sys.argv[1], sys.argv[2], int(sys.argv[3])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
sc = bpy.context.scene
meshes = [o for o in sc.objects if o.type == 'MESH']
lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c); lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
size = hi - lo; ctr = (lo + hi) / 2
print('SIZE', size.x, size.y, size.z)
sc.render.engine = 'CYCLES'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.film_transparent = True
H = max(size.z, max(size.x, size.y) * 2) * 1.02
sc.render.resolution_y = res; sc.render.resolution_x = int(res * max(size.x, size.y) * 1.04 / H * 1.0) if size.z * 0.5 >= max(size.x, size.y) else res // 2
sc.render.resolution_x = max(64, int(res * (max(size.x, size.y) * 1.04) / (size.z * 1.02)))
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1); bg.inputs[1].default_value = 0.9
ld = bpy.data.lights.new('sun', 'SUN'); ld.energy = 3.2; ld.angle = 0.1
lo_ = bpy.data.objects.new('sun', ld); sc.collection.objects.link(lo_); lo_.rotation_euler = (math.radians(50), 0, math.radians(30))
cd = bpy.data.cameras.new('c'); cd.type = 'ORTHO'; cd.ortho_scale = max(size.z * 1.02, max(size.x, size.y) * 1.04)
cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
for i, ang in enumerate((0, 90)):
    a = math.radians(ang)
    d = 50
    cam.location = (ctr.x + math.sin(a) * d, ctr.y - math.cos(a) * d, ctr.z)
    cam.rotation_euler = (math.radians(90), 0, a)
    lo_.rotation_euler = (math.radians(50), 0, a + math.radians(35))
    sc.render.filepath = f'{out}_{i}.png'
    bpy.ops.render.render(write_still=True)
print('ASPECT', sc.render.resolution_x / sc.render.resolution_y, 'HEIGHT', size.z)
