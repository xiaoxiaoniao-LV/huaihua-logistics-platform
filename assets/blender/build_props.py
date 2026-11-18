"""可复用道具：冷藏货车、月台门、冷链箱。

三者都按真实尺寸建模，原点在底面中心，朝向 +X 为车头/正面。
"""

import math

import bpy

from bl_common import Part, _material, add_empty, bevel, palette


def _extra_materials():
    P = palette()
    if "wood" not in P:
        P["wood"] = _material("M_PalletWood", (0.42, 0.31, 0.19), 0.0, 0.80)
    if "alu" not in P:
        P["alu"] = _material("M_Aluminium", (0.80, 0.82, 0.85), 0.55, 0.28)
    if "ice" not in P:
        P["ice"] = _material("M_ColdInterior", (0.72, 0.78, 0.82), 0.20, 0.50)
    return P


# ---------------------------------------------------------------- 月台门
def dock(name, base, lod="hi"):
    """base=(x, y_wall, 0)，门洞朝 -Y 外侧。"""
    P = _extra_materials()
    x, y, _ = base
    seg = 24 if lod == "hi" else 12
    objs = []

    frame = Part(f"{name}_Frame", P["galv"])
    frame.box((0.28, 0.34, 3.9), (x - 1.66, y - 0.12, 1.95))
    frame.box((0.28, 0.34, 3.9), (x + 1.66, y - 0.12, 1.95))
    frame.box((3.6, 0.34, 0.28), (x, y - 0.12, 3.9))
    frame.box((3.6, 0.20, 0.12), (x, y - 0.18, 4.12))
    objs.append(frame.build())

    door = Part(f"{name}_Door", P["white"])
    step = 0.20 if lod == "hi" else 0.42
    z = 0.12
    while z < 3.72:
        h = min(step - 0.02, 3.72 - z)
        door.box((3.16, 0.07, h), (x, y - 0.05, z + h / 2))
        z += step
    objs.append(door.build())

    seal = Part(f"{name}_Seal", P["rubber"])
    seal.box((0.42, 0.40, 3.55), (x - 1.83, y - 0.34, 1.80))
    seal.box((0.42, 0.40, 3.55), (x + 1.83, y - 0.34, 1.80))
    seal.box((4.08, 0.40, 0.42), (x, y - 0.34, 3.58))
    objs.append(seal.build())

    bumper = Part(f"{name}_Bumpers", P["rubber"])
    bumper.box((0.62, 0.28, 0.46), (x - 2.25, y - 0.28, 0.92))
    bumper.box((0.62, 0.28, 0.46), (x + 2.25, y - 0.28, 0.92))
    objs.append(bumper.build())

    leveler = Part(f"{name}_Leveler", P["steel_dark"])
    leveler.box((2.6, 3.0, 0.10), (x, y - 1.9, 0.05))
    objs.append(leveler.build())

    light = Part(f"{name}_DockLight", P["warm"])
    light.box((0.26, 0.22, 0.16), (x, y - 0.55, 4.32))
    objs.append(light.build())

    objs.append(add_empty(f"Anchor_{name}", (x, y - 0.6, 4.4)))
    if lod == "hi":
        bevel(objs[0], 0.02, 2)
    return objs


# ---------------------------------------------------------------- 冷藏货车
def truck(name, loc=(0, 0, 0), yaw=0.0, lod="hi"):
    """9.6m 厢式冷藏车，车头朝 +X，轮胎着地 z=0。"""
    P = _extra_materials()
    seg = 24 if lod == "hi" else 12
    root = add_empty(name, loc)
    root.rotation_euler = (0, 0, math.radians(yaw))
    objs = [root]

    chassis = Part(f"{name}_Chassis", P["steel_dark"])
    chassis.box((10.4, 1.9, 0.34), (0.4, 0, 0.92))
    chassis.box((10.4, 0.16, 0.28), (0.4, 1.05, 0.86))
    chassis.box((10.4, 0.16, 0.28), (0.4, -1.05, 0.86))
    objs.append(chassis.build())

    body = Part(f"{name}_Box", P["white"])
    body.box((9.6, 2.5, 2.85), (-0.2, 0, 2.34))
    # 厢体下沿补板：填掉厢体与底盘之间的空隙
    body.box((9.6, 2.44, 0.34), (-0.2, 0, 0.93))
    if lod == "hi":
        for i in range(16):
            px = -4.85 + i * 0.6
            body.box((0.05, 2.54, 2.6), (px, 0, 2.34))
    objs.append(body.build())

    trim = Part(f"{name}_Trim", P["alu"])
    trim.box((9.66, 0.10, 0.14), (-0.2, 1.27, 0.98))
    trim.box((9.66, 0.10, 0.14), (-0.2, -1.27, 0.98))
    trim.box((9.66, 0.10, 0.14), (-0.2, 1.27, 3.70))
    trim.box((9.66, 0.10, 0.14), (-0.2, -1.27, 3.70))
    trim.box((0.10, 2.54, 2.85), (-5.02, 0, 2.34))
    objs.append(trim.build())

    doors = Part(f"{name}_RearDoors", P["steel"])
    doors.box((0.10, 1.20, 2.70), (-5.02, 0.62, 2.34))
    doors.box((0.10, 1.20, 2.70), (-5.02, -0.62, 2.34))
    if lod == "hi":
        # 横向锁杆 + 铰链
        for zz in (1.15, 1.75, 2.35, 2.95, 3.55):
            doors.box((0.07, 1.26, 0.08), (-5.09, 0, zz))
        for zz in (1.10, 2.30, 3.60):
            doors.box((0.12, 0.10, 0.22), (-5.06, 1.20, zz))
            doors.box((0.12, 0.10, 0.22), (-5.06, -1.20, zz))
    objs.append(doors.build())

    cab = Part(f"{name}_Cab", P["steel"])
    cab.box((2.25, 2.36, 1.95), (5.60, 0, 2.10))
    cab.box((2.10, 2.30, 0.55), (5.60, 0, 3.30))   # 顶盖
    cab.box((1.70, 2.28, 0.62), (4.92, 0, 3.62))   # 导流罩
    objs.append(cab.build())

    dark = Part(f"{name}_Details", P["steel_dark"])
    dark.box((0.12, 1.70, 0.52), (6.72, 0, 1.58))  # 前格栅
    dark.box((0.70, 0.22, 0.34), (5.95, 1.12, 1.02))  # 上车踏板
    dark.box((0.70, 0.22, 0.34), (5.95, -1.12, 1.02))
    dark.box((0.12, 2.20, 0.16), (-5.15, 0, 0.58))  # 后防撞杆
    dark.box((0.05, 0.34, 0.05), (6.32, 1.30, 2.96))  # 后视镜支臂
    dark.box((0.05, 0.34, 0.05), (6.32, -1.30, 2.96))
    dark.box((0.05, 0.16, 0.46), (6.28, 1.47, 2.80))
    dark.box((0.05, 0.16, 0.46), (6.28, -1.47, 2.80))
    objs.append(dark.build())

    glass = Part(f"{name}_Glass", P["glass"])
    glass.box((0.12, 2.10, 1.00), (6.68, 0, 2.55))
    glass.box((1.25, 0.06, 0.80), (5.58, 1.185, 2.62))
    glass.box((1.25, 0.06, 0.80), (5.58, -1.185, 2.62))
    objs.append(glass.build())

    reefer = Part(f"{name}_Reefer", P["white"])
    reefer.box((0.55, 2.20, 1.00), (4.72, 0, 3.15))
    objs.append(reefer.build())
    fan = Part(f"{name}_ReeferFan", P["steel_dark"])
    fan.cyl(0.40, 0.12, (5.02, 0, 3.20), rot=(0, math.pi / 2, 0), seg=seg)
    objs.append(fan.build(smooth=True))

    wheels = Part(f"{name}_Wheels", P["rubber"])
    hubs = Part(f"{name}_Hubs", P["alu"])
    for ax, pairs in ((6.10, 1), (-3.95, 1), (-2.55, 1)):
        for sy in (-1, 1):
            wheels.cyl(0.52, 0.30, (ax, sy * 1.10, 0.52), rot=(math.pi / 2, 0, 0), seg=seg)
            hubs.cyl(0.26, 0.32, (ax, sy * 1.10, 0.52), rot=(math.pi / 2, 0, 0), seg=seg)
    objs.append(wheels.build(smooth=True))
    objs.append(hubs.build(smooth=True))

    mud = Part(f"{name}_Mudguard", P["steel_dark"])
    for ax in (-3.95, -2.55):
        mud.box((1.1, 2.32, 0.10), (ax, 0, 1.12))
    objs.append(mud.build())

    bumper = Part(f"{name}_Bumper", P["steel_dark"])
    bumper.box((0.20, 2.30, 0.42), (7.04, 0, 0.78))
    objs.append(bumper.build())

    lights = Part(f"{name}_Lights", P["warm"])
    lights.box((0.10, 0.34, 0.18), (7.02, 0.86, 1.06))
    lights.box((0.10, 0.34, 0.18), (7.02, -0.86, 1.06))
    objs.append(lights.build())

    tail = Part(f"{name}_TailLights", P["red"])
    tail.box((0.08, 0.26, 0.16), (-5.06, 0.86, 1.10))
    tail.box((0.08, 0.26, 0.16), (-5.06, -0.86, 1.10))
    objs.append(tail.build())

    if lod == "hi":
        for ob in objs:
            if ob.type == "MESH" and ob.name.endswith(("_Cab", "_Box", "_Reefer")):
                bevel(ob, 0.04, 2)

    for ob in objs[1:]:
        ob.parent = root
    objs.append(add_empty(f"Anchor_{name}", (0, 0, 4.3), parent=root))
    return objs


# ---------------------------------------------------------------- 冷链箱
def coldbox(name, loc=(0, 0, 0), yaw=0.0, lod="hi"):
    """1.2×1.0×1.7m 冷链保温箱（含托盘），原点在底面中心。"""
    P = _extra_materials()
    seg = 20 if lod == "hi" else 10
    root = add_empty(name, loc)
    root.rotation_euler = (0, 0, math.radians(yaw))
    objs = [root]

    pallet = Part(f"{name}_Pallet", P["wood"])
    pallet.box((1.20, 1.00, 0.14), (0, 0, 0.07))
    if lod == "hi":
        for sx in (-0.44, 0.0, 0.44):
            pallet.box((0.20, 1.00, 0.06), (sx, 0, 0.03))
    objs.append(pallet.build())

    shell = Part(f"Body_{name}_Shell", P["body"])
    shell.box((1.14, 0.94, 1.50), (0, 0, 0.14 + 0.75))
    objs.append(shell.build())

    alu = Part(f"{name}_Frame", P["alu"])
    for sx in (-0.57, 0.57):
        for sy in (-0.47, 0.47):
            alu.box((0.055, 0.055, 1.50), (sx, sy, 0.89))
            for cz in (0.19, 1.60):  # 8 个包角
                alu.box((0.13, 0.13, 0.11), (sx, sy, cz))
    alu.box((1.20, 0.94, 0.05), (0, 0, 1.655))
    alu.box((1.20, 0.94, 0.05), (0, 0, 0.165))
    objs.append(alu.build())

    lid = Part(f"{name}_Lid", P["ice"])
    lid.box((1.05, 0.85, 0.03), (0, 0, 1.675))
    objs.append(lid.build())

    door = Part(f"Body_{name}_Door", P["white"])
    door.box((0.98, 0.05, 1.28), (0, 0.475, 0.95))
    objs.append(door.build())

    hinge = Part(f"{name}_Hinges", P["alu"])
    for zz in (0.55, 1.35):
        hinge.box((0.10, 0.06, 0.10), (-0.50, 0.50, zz))
    objs.append(hinge.build())

    latch = Part(f"{name}_Latch", P["steel_dark"])
    latch.box((0.08, 0.07, 0.24), (0.47, 0.50, 1.00))
    objs.append(latch.build())

    panel = Part(f"Device_{name}_Panel", P["steel_dark"])
    panel.box((0.24, 0.045, 0.13), (0.30, 0.50, 1.50))
    objs.append(panel.build())

    display = Part(f"Device_{name}_Display", P["cyan"])
    display.box((0.15, 0.02, 0.07), (0.30, 0.525, 1.50))
    objs.append(display.build())

    vent = Part(f"{name}_Vent", P["steel_dark"])
    vent.box((0.035, 0.60, 0.36), (-0.585, 0, 0.72))
    if lod == "hi":
        for i in range(7):
            vent.box((0.02, 0.56, 0.02), (-0.605, 0, 0.57 + i * 0.05))
    objs.append(vent.build())

    vent2 = Part(f"{name}_Vent2", P["rubber"])
    vent2.box((0.46, 0.035, 0.30), (0.30, -0.485, 0.78))
    objs.append(vent2.build())

    if lod == "hi":
        for ob in objs:
            if ob.type == "MESH" and ob.name.startswith("Body_"):
                bevel(ob, 0.035, 3)

    for ob in objs[1:]:
        ob.parent = root
    objs.append(add_empty(f"Anchor_{name}", (0, 0, 1.95), parent=root))
    return objs
