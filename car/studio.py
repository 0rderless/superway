"""Shared studio: black world, dark glossy floor fading to black, overhead pool + strip softboxes,
AgX Medium High Contrast, glare/bloom, vignette, grain.

API
    setup_studio(scene=None, samples=64, res=(1472, 816), compositor=True) -> dict of objects
    setup_render(scene, samples, res)
"""
import bpy, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _emit_mat(name, strength, color=(1, 1, 1), pattern=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    if pattern == 'skylight':
        # skylight panel: bright panes separated by dark mullions + a few diagonal struts
        tc = nt.nodes.new('ShaderNodeTexCoord')
        mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (5.0, 3.0, 1)
        nt.links.new(tc.outputs['UV'], mp.inputs['Vector'])
        br = nt.nodes.new('ShaderNodeTexBrick')
        br.inputs['Color1'].default_value = (1, 1, 1, 1); br.inputs['Color2'].default_value = (0.85, 0.85, 0.85, 1)
        br.inputs['Mortar'].default_value = (0.03, 0.03, 0.03, 1)
        br.inputs['Mortar Size'].default_value = 0.035
        br.inputs['Scale'].default_value = 1.0
        br.offset = 0.0
        nt.links.new(mp.outputs['Vector'], br.inputs['Vector'])
        # soft falloff toward the panel edges
        sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['UV'], sep.inputs['Vector'])
        gx = nt.nodes.new('ShaderNodeMath'); gx.operation = 'PINGPONG'; gx.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs['X'], gx.inputs[0])
        gy = nt.nodes.new('ShaderNodeMath'); gy.operation = 'PINGPONG'; gy.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs['Y'], gy.inputs[0])
        mm = nt.nodes.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'
        nt.links.new(gx.outputs[0], mm.inputs[0]); nt.links.new(gy.outputs[0], mm.inputs[1])
        mr = nt.nodes.new('ShaderNodeMapRange'); mr.inputs['From Max'].default_value = 0.05
        nt.links.new(mm.outputs[0], mr.inputs['Value'])
        mul = nt.nodes.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'
        mul.inputs['Factor'].default_value = 1.0
        nt.links.new(br.outputs['Color'], mul.inputs[6])
        nt.links.new(mr.outputs[0], mul.inputs[7])
        nt.links.new(mul.outputs[2], em.inputs['Color'])
    elif pattern == 'strip':
        # bright core, soft edges across the short axis (UV y)
        tc = nt.nodes.new('ShaderNodeTexCoord')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['UV'], sep.inputs['Vector'])
        pp = nt.nodes.new('ShaderNodeMath'); pp.operation = 'PINGPONG'; pp.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs['Y'], pp.inputs[0])
        mr = nt.nodes.new('ShaderNodeMapRange'); mr.inputs['From Max'].default_value = 0.25
        nt.links.new(pp.outputs[0], mr.inputs['Value'])
        px = nt.nodes.new('ShaderNodeMath'); px.operation = 'PINGPONG'; px.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs['X'], px.inputs[0])
        mx = nt.nodes.new('ShaderNodeMapRange'); mx.inputs['From Max'].default_value = 0.08
        nt.links.new(px.outputs[0], mx.inputs['Value'])
        mm = nt.nodes.new('ShaderNodeMath'); mm.operation = 'MULTIPLY'
        nt.links.new(mr.outputs[0], mm.inputs[0]); nt.links.new(mx.outputs[0], mm.inputs[1])
        ms = nt.nodes.new('ShaderNodeMath'); ms.operation = 'MULTIPLY'; ms.inputs[1].default_value = strength
        nt.links.new(mm.outputs[0], ms.inputs[0])
        nt.links.new(ms.outputs[0], em.inputs['Strength'])
    nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m


def _panel(name, size, loc, rot, mat, col):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    o.scale = (size[0], size[1], 1)
    o.data.materials.append(mat)
    o.visible_camera = False
    o.visible_shadow = False
    o.visible_diffuse = False
    o.visible_volume_scatter = False
    if col is not None:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
    return o


def _floor_mat():
    m = bpy.data.materials.new('Floor')
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    p.inputs['Roughness'].default_value = 0.35
    p.inputs['Specular IOR Level'].default_value = 0.2
    # albedo fades to black with distance from the car
    tc = nt.nodes.new('ShaderNodeTexCoord')
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'
    nt.links.new(tc.outputs['Object'], ln.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 2.5; mr.inputs['From Max'].default_value = 8.0
    mr.inputs['To Min'].default_value = 1.0; mr.inputs['To Max'].default_value = 0.0
    nt.links.new(ln.outputs['Value'], mr.inputs['Value'])
    c = nt.nodes.new('ShaderNodeMix'); c.data_type = 'RGBA'
    c.inputs[6].default_value = (0.0, 0.0, 0.0, 1); c.inputs[7].default_value = (0.035, 0.035, 0.037, 1)
    nt.links.new(mr.outputs[0], c.inputs['Factor'])
    nt.links.new(c.outputs[2], p.inputs['Base Color'])
    # subtle large-scale roughness variation
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 0.6
    r = nt.nodes.new('ShaderNodeMapRange'); r.inputs['To Min'].default_value = 0.24; r.inputs['To Max'].default_value = 0.36
    nt.links.new(nz.outputs['Fac'], r.inputs['Value']); nt.links.new(r.outputs[0], p.inputs['Roughness'])
    # reflection weakens with distance as well
    s = nt.nodes.new('ShaderNodeMapRange'); s.inputs['To Min'].default_value = 0.0; s.inputs['To Max'].default_value = 0.25
    nt.links.new(mr.outputs[0], s.inputs['Value']); nt.links.new(s.outputs[0], p.inputs['Specular IOR Level'])
    return m


def setup_render(sc, samples=64, res=(1472, 816)):
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    sc.cycles.max_bounces = 8; sc.cycles.glossy_bounces = 4; sc.cycles.transmission_bounces = 8
    sc.cycles.diffuse_bounces = 3; sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 0.5
    sc.render.threads_mode = 'FIXED'; sc.render.threads = 4
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.view_settings.exposure = -0.4
    sc.render.image_settings.file_format = 'PNG'


def _grain_image(w, h):
    path = os.path.join(HERE, 'out', '_grain_%dx%d.png' % (w, h))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rng = np.random.default_rng(7)
        g = rng.normal(0.5, 0.18, (h, w))
        g = np.clip(g, 0, 1)
        img = bpy.data.images.new('_grain_tmp', w, h, alpha=False, float_buffer=True)
        px = np.repeat(g[::-1].reshape(-1, 1), 4, 1); px[:, 3] = 1
        img.pixels.foreach_set(px.ravel().astype(np.float32))
        img.filepath_raw = path; img.file_format = 'PNG'; img.save()
        bpy.data.images.remove(img)
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = 'Non-Color'
    return im


def setup_compositor(sc):
    w, h = sc.render.resolution_x, sc.render.resolution_y
    ng = bpy.data.node_groups.new('StudioComp', 'CompositorNodeTree')
    sc.compositing_node_group = ng
    ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    N = ng.nodes; Lk = ng.links
    rl = N.new('CompositorNodeRLayers')
    gl = N.new('CompositorNodeGlare')
    gl.inputs['Type'].default_value = 'Bloom'
    gl.inputs['Threshold'].default_value = 1.6
    gl.inputs['Strength'].default_value = 0.18
    gl.inputs['Size'].default_value = 0.55
    Lk.new(rl.outputs['Image'], gl.inputs['Image'])
    # vignette
    el = N.new('CompositorNodeEllipseMask')
    el.inputs['Size'].default_value = (0.95, 0.85)
    bl = N.new('CompositorNodeBlur')
    bl.inputs['Size'].default_value = (int(w * 0.25), int(h * 0.25))
    Lk.new(el.outputs['Mask'], bl.inputs['Image'])
    mr = N.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.55; mr.inputs['To Max'].default_value = 1.0
    Lk.new(bl.outputs['Image'], mr.inputs['Value'])
    vg = N.new('ShaderNodeMix'); vg.data_type = 'RGBA'; vg.blend_type = 'MULTIPLY'
    vg.inputs['Factor'].default_value = 1.0
    Lk.new(gl.outputs['Image'], vg.inputs[6]); Lk.new(mr.outputs[0], vg.inputs[7])
    # grain (soft light with fixed noise image)
    gi = N.new('CompositorNodeImage'); gi.image = _grain_image(w, h)
    gr = N.new('ShaderNodeMix'); gr.data_type = 'RGBA'; gr.blend_type = 'SOFT_LIGHT'
    gr.inputs['Factor'].default_value = 0.10
    Lk.new(vg.outputs[2], gr.inputs[6]); Lk.new(gi.outputs['Image'], gr.inputs[7])
    out = N.new('NodeGroupOutput')
    Lk.new(gr.outputs[2], out.inputs[0])
    return ng


def setup_studio(sc=None, samples=64, res=(1472, 816), compositor=True, col=None):
    sc = sc or bpy.context.scene
    setup_render(sc, samples, res)
    if col is None:
        col = bpy.data.collections.new('Studio'); sc.collection.children.link(col)
    w = bpy.data.worlds.new('Black'); sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    if bg:
        bg.inputs[0].default_value = (0, 0, 0, 1); bg.inputs[1].default_value = 0.0
    objs = {}
    # floor
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    fl = bpy.context.active_object; fl.name = 'Floor'
    fl.data.materials.append(_floor_mat())
    for c in fl.users_collection:
        c.objects.unlink(fl)
    col.objects.link(fl); objs['Floor'] = fl
    # overhead soft pool (area light, does most of the illumination)
    ld = bpy.data.lights.new('TopPool', 'AREA'); ld.shape = 'ELLIPSE'
    ld.size = 5.5; ld.size_y = 3.8; ld.energy = 130; ld.spread = math.radians(55)
    lo = bpy.data.objects.new('TopPool', ld); col.objects.link(lo); lo.location = (0, 0, 5.2)
    lo.visible_glossy = False
    objs['TopPool'] = lo
    # visible-in-reflection skylight panel with mullions (structured reflections like the reference)
    sky = _panel('Skylight', (6.5, 4.0), (0.3, 0, 5.0), (math.pi, 0, 0), _emit_mat('SkyEmit', 2.2, pattern='skylight'), col)
    objs['Skylight'] = sky
    # long strip softboxes either side + front/rear (crisp reflection streaks)
    strip = _emit_mat('StripEmit', 6.0, pattern='strip')
    for s in (1, -1):
        o = _panel('StripSide%+d' % s, (9.0, 0.45), (0, s * 4.6, 2.3), (s * math.radians(-62), 0, 0), strip, col)
        o.rotation_euler = (math.radians(90 - 28) * s, 0, 0) if False else o.rotation_euler
        objs['StripSide%+d' % s] = o
        o2 = _panel('StripHigh%+d' % s, (8.0, 0.3), (0, s * 2.6, 4.1), (s * math.radians(-30), 0, 0), strip, col)
        objs['StripHigh%+d' % s] = o2
    # low side strips: grey reflection streaks on the gloss-black rims and lower body (wheel close-ups)
    low = _emit_mat('LowEmit', 2.2, pattern='strip')
    for s in (1, -1):
        o = _panel('StripLow%+d' % s, (7.0, 0.5), (0, s * 3.2, 0.35), (s * math.radians(-95), 0, 0), low, col)
        objs['StripLow%+d' % s] = o
    # wheel kickers: panels front/rear of each side so the gloss-black spokes pick up grey reflections
    kick = _emit_mat('KickEmit', 3.0, pattern=None)
    for sx in (1, -1):
        for sy in (1, -1):
            p = np.array([sx * 3.4, sy * 3.0, 1.1])
            o = _panel('StripKick%+d%+d' % (sx, sy), (2.6, 1.4), tuple(p), (0, 0, 0), kick, col)
            d = -p + np.array([0, 0, 0.6]); d /= np.linalg.norm(d)
            from mathutils import Vector as _V
            o.rotation_euler = _V(tuple(d)).to_track_quat('Z', 'Y').to_euler()
            objs[o.name] = o
    for s in (1, -1):
        o = _panel('StripEnd%+d' % s, (0.35, 3.5), (s * 5.2, 0, 2.6), (0, s * math.radians(55), 0), _emit_mat('EndEmit', 6.0, pattern=None), col)
        objs['StripEnd%+d' % s] = o
    # front / rear diffuse fills (the reference shows the nose and the tail face lit)
    for s_, nm in ((1, 'FillFront'), (-1, 'FillRear')):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.size = 3.5; ld.size_y = 1.5; ld.energy = 70 if s_ > 0 else 160
        lo = bpy.data.objects.new(nm, ld); col.objects.link(lo)
        lo.location = (s_ * 5.5, 0, 1.6); lo.rotation_euler = (0, s_ * math.radians(75), 0)
        lo.visible_glossy = False
    # weak rim fill so lower body sides are not pure black
    for s in (1, -1):
        ld = bpy.data.lights.new('Fill%+d' % s, 'AREA'); ld.size = 6; ld.size_y = 1.2; ld.energy = 45
        lo = bpy.data.objects.new('Fill%+d' % s, ld); col.objects.link(lo)
        lo.location = (0, s * 5.0, 1.2); lo.rotation_euler = (s * math.radians(-80), 0, 0)
        lo.visible_glossy = False
    if compositor:
        setup_compositor(sc)
    return objs


def link_lights_to(objs, receiver_col):
    """reflection panels only light/reflect in the car (keeps the floor dark like the reference)."""
    for n, o in objs.items():
        if n.startswith(('Skylight', 'Strip')):
            o.light_linking.receiver_collection = receiver_col
