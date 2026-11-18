"""Blender 建模公共层：材质、几何、导出、统计、预览渲染。

约定（前端依赖）：
- 单位：米；原点在物体底面中心；Blender Z 向上，导出 glTF 时转 Y 向上。
- 命名：`Body_` 前缀 = 状态着色层；`Device_` 前缀 = 可点击设备；
  `Anchor_` 前缀 = 空的定位锚点（供 HTML 标签挂载）。
"""

import math
import os
import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

PALETTE = {}


# ---------------------------------------------------------------- 场景与材质
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    PALETTE.clear()


def _material(name, color, metallic=0.0, roughness=0.6, emission=None, strength=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = roughness
    if emission is not None:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    return m


def palette():
    if PALETTE:
        return PALETTE
    PALETTE.update(
        {
            "steel": _material("M_SteelClad", (0.72, 0.75, 0.79), 0.30, 0.44),
            "steel_dark": _material("M_SteelDark", (0.16, 0.19, 0.23), 0.35, 0.40),
            "galv": _material("M_Galvanized", (0.62, 0.65, 0.69), 0.42, 0.34),
            "deck": _material("M_RackDeck", (0.34, 0.36, 0.39), 0.30, 0.55),
            "concrete": _material("M_Concrete", (0.30, 0.31, 0.33), 0.0, 0.88),
            "epoxy": _material("M_EpoxyFloor", (0.20, 0.22, 0.26), 0.05, 0.52),
            "asphalt": _material("M_Asphalt", (0.10, 0.11, 0.12), 0.0, 0.92),
            "white": _material("M_PanelWhite", (0.82, 0.85, 0.88), 0.25, 0.45),
            "orange": _material("M_SafetyOrange", (0.82, 0.33, 0.03), 0.10, 0.55),
            "yellow": _material("M_SafetyYellow", (0.85, 0.68, 0.05), 0.0, 0.60),
            "rubber": _material("M_Rubber", (0.025, 0.025, 0.03), 0.0, 0.92),
            "blue": _material("M_RackBlue", (0.06, 0.22, 0.48), 0.55, 0.38),
            "glass": _material("M_GlassDark", (0.04, 0.07, 0.10), 0.60, 0.12),
            "cyan": _material("M_EmitCyan", (0.05, 0.55, 0.75), 0.0, 0.35, (0.10, 0.85, 1.0), 3.0),
            "warm": _material("M_EmitWarm", (0.95, 0.92, 0.85), 0.0, 0.40, (1.0, 0.95, 0.85), 2.5),
            "body": _material("M_BodyStatus", (0.10, 0.62, 0.78), 0.15, 0.42, (0.05, 0.55, 0.75), 0.35),
            "red": _material("M_EmitRed", (0.60, 0.05, 0.05), 0.0, 0.40, (1.0, 0.10, 0.10), 2.0),
        }
    )
    return PALETTE


# ---------------------------------------------------------------- 几何原语
def put_box(bm, size, loc=(0, 0, 0), rot=(0, 0, 0)):
    m = (
        Matrix.Translation(Vector(loc))
        @ Euler(rot, "XYZ").to_matrix().to_4x4()
        @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    )
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def put_cyl(bm, r, h, loc=(0, 0, 0), rot=(0, 0, 0), seg=24, r2=None):
    m = Matrix.Translation(Vector(loc)) @ Euler(rot, "XYZ").to_matrix().to_4x4()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=seg,
        radius1=r,
        radius2=r if r2 is None else r2,
        depth=h,
        matrix=m,
    )


class Part:
    """一个对象 = 一个材质 + 一个 bmesh，便于命名与按材质合批。"""

    def __init__(self, name, material):
        self.name = name
        self.material = material
        self.bm = bmesh.new()

    def box(self, size, loc=(0, 0, 0), rot=(0, 0, 0)):
        put_box(self.bm, size, loc, rot)
        return self

    def cyl(self, r, h, loc=(0, 0, 0), rot=(0, 0, 0), seg=24, r2=None):
        put_cyl(self.bm, r, h, loc, rot, seg, r2)
        return self

    def build(self, smooth=False):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        if smooth:
            for p in me.polygons:
                p.use_smooth = True
        ob = bpy.data.objects.new(self.name, me)
        if self.material:
            me.materials.append(self.material)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def add_empty(name, loc, parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.5
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    return ob


def bevel(ob, width=0.02, segments=2):
    md = ob.modifiers.new("Bevel", "BEVEL")
    md.width = width
    md.segments = segments
    md.limit_method = "ANGLE"
    md.angle_limit = 0.5
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=md.name)
    return ob


# ---------------------------------------------------------------- 统计与导出
def tri_count(objs):
    n = 0
    for o in objs:
        if o.type != "MESH":
            continue
        for p in o.data.polygons:
            n += max(0, len(p.vertices) - 2)
    return n


def world_bbox(objs):
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    hit = False
    for o in objs:
        if o.type != "MESH":
            continue
        hit = True
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector((min(mn.x, w.x), min(mn.y, w.y), min(mn.z, w.z)))
            mx = Vector((max(mx.x, w.x), max(mx.y, w.y), max(mx.z, w.z)))
    if not hit:
        return [0, 0, 0], [0, 0, 0], [0, 0, 0]
    size = [round(mx[i] - mn[i], 3) for i in range(3)]
    return size, [round(v, 3) for v in mn], [round(v, 3) for v in mx]


def export_glb(path, objs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
    )
    return os.path.getsize(path)


# ---------------------------------------------------------------- 预览渲染
def setup_studio(
    bg=(0.012, 0.016, 0.024),
    engine="BLENDER_EEVEE_NEXT",
    center=(0, 0, 0),
    radius=10.0,
    direction=(0.8, -1.0, 0.62),
):
    """摄影棚布光。灯光位置/功率随尺度缩放，主光跟随相机方位，保证朝向镜头的一面受光。"""
    sc = bpy.context.scene
    sc.render.engine = engine
    if engine == "CYCLES":
        sc.cycles.samples = 48
        sc.cycles.use_denoising = True
        sc.cycles.device = "CPU"
    else:
        sc.eevee.taa_render_samples = 32
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (*bg, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = world

    c = Vector(center)
    s = max(radius, 0.5)
    d = Vector(direction).normalized()
    up = Vector((0.0, 0.0, 1.0))
    right = d.cross(up)
    if right.length < 1e-4:
        right = Vector((1.0, 0.0, 0.0))
    right.normalize()

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 42.0 * s * s
    key.size = 0.8 * s
    ko = bpy.data.objects.new("Key", key)
    ko.location = c + (d * 2.3 + right * 0.9 + up * 1.0) * s
    ko.rotation_euler = (c - ko.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(ko)

    rim = bpy.data.lights.new("Rim", "AREA")
    rim.energy = 20.0 * s * s
    rim.size = 0.7 * s
    rim.color = (0.55, 0.75, 1.0)
    ro = bpy.data.objects.new("Rim", rim)
    ro.location = c + (-d * 1.9 - right * 1.1 + up * 1.5) * s
    ro.rotation_euler = (c - ro.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(ro)

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 1.6
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (0.55, 0.15, 0.9)
    sc.collection.objects.link(so)


def add_camera(loc, target, lens=45):
    cam = bpy.data.cameras.new("Cam")
    cam.lens = lens
    co = bpy.data.objects.new("Cam", cam)
    co.location = loc
    bpy.context.scene.collection.objects.link(co)
    bpy.context.scene.camera = co
    d = Vector(target) - Vector(loc)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return co


def frame_camera(objs, direction=(0.8, -1.0, 0.62), lens=50.0, res=(1400, 788), margin=1.06):
    """按包围盒自动取景：相机沿 direction 方向后退到刚好装下模型。"""
    size, mn, mx = world_bbox(objs)
    center = Vector(((mn[i] + mx[i]) / 2.0 for i in range(3)))
    fov_h = 2.0 * math.atan(18.0 / lens)
    fov_v = 2.0 * math.atan(18.0 * res[1] / res[0] / lens)
    r = 0.5 * max(size) * margin
    d = r / math.sin(min(fov_h, fov_v) / 2.0)
    loc = center + Vector(direction).normalized() * d
    return add_camera(loc, center, lens)


def render_to(path, res=(1280, 720)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.getsize(path) if os.path.exists(path) else 0
