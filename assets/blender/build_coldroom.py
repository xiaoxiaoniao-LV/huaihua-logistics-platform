"""L2 冷库内部：地面、围护、6 排双面货架、层板、灯带、冷风机、货位锚点。

真实尺度：库房 54×38×12m；立柱高 9m，横梁跨 2.7m（3 个欧标托盘），
单面进深 1.1m，通道 3.8m。货位锚点命名 Anchor_Slot_R{排}C{列}L{层}S{面}。
"""

import math

import bpy

from bl_common import Part, add_empty, bevel, palette
import build_props

ROOM = (54.0, 38.0, 12.0)
ROWS = [-15.0, -9.0, -3.0, 3.0, 9.0, 15.0]
COLS = 18
BAY = 2.7
LEVELS = [1.5, 4.0, 6.5]
RACK_H = 9.0
SIDE_OFF = 0.55
RACK_LEN = COLS * BAY


# ---------------------------------------------------------------- 地面与围护
def _shell(lod):
    P = palette()
    W, D, H = ROOM
    objs = []

    floor = Part("Shell_Floor", P["epoxy"])
    floor.box((W, D, 0.20), (0, 0, -0.10))
    objs.append(floor.build())

    # 后墙、左右墙：冷库保温板
    panels = Part("Shell_WallPanels", P["white"])
    panels.box((W, 0.30, H), (0, D / 2 - 0.15, H / 2))
    panels.box((0.30, D, H), (-W / 2 + 0.15, 0, H / 2))
    panels.box((0.30, D, H), (W / 2 - 0.15, 0, H / 2))
    # 前墙做 4.2m 剖切墙，按两个月台门开洞，以上敞开以便俯视库内
    fy = -D / 2 + 0.15
    fh = 4.2
    edges = [(-W / 2, -11.0), (-7.0, 7.0), (11.0, W / 2)]
    for a, b in edges:
        panels.box((b - a, 0.30, fh), ((a + b) / 2, fy, fh / 2))
    for dx in (-9.0, 9.0):
        panels.box((4.0, 0.30, fh - 3.8), (dx, fy, (fh + 3.8) / 2))
    objs.append(panels.build())

    seams = Part("Shell_WallSeams", P["galv"])
    step = 1.2 if lod == "hi" else 2.4
    x = -W / 2 + step
    while x < W / 2 - 0.3:
        seams.box((0.05, 0.04, H - 0.4), (x, D / 2 - 0.32, H / 2))
        x += step
    y = -D / 2 + step
    while y < D / 2 - 0.3:
        seams.box((0.04, 0.05, H - 0.4), (-W / 2 + 0.32, y, H / 2))
        seams.box((0.04, 0.05, H - 0.4), (W / 2 - 0.32, y, H / 2))
        y += step
    objs.append(seams.build())

    # 屋面钢梁（不封顶，保证俯视可见内部）
    girders = Part("Shell_RoofGirders", P["steel_dark"])
    yy = -D / 2 + 3.0
    while yy < D / 2:
        girders.box((W, 0.22, 0.55), (0, yy, H - 0.45))
        yy += 6.0
    girders.box((0.3, D, 0.6), (-W / 2 + 0.4, 0, H - 0.42))
    girders.box((0.3, D, 0.6), (W / 2 - 0.4, 0, H - 0.42))
    objs.append(girders.build())

    # 地面通道标线
    lines = Part("Shell_FloorLines", P["yellow"])
    for ry in ROWS:
        lines.box((RACK_LEN + 4.0, 0.14, 0.02), (0, ry + 2.9, 0.01))
    lines.box((0.16, D - 4.0, 0.02), (-W / 2 + 2.2, 0, 0.01))
    lines.box((0.16, D - 4.0, 0.02), (W / 2 - 2.2, 0, 0.01))
    objs.append(lines.build())
    return objs


# ---------------------------------------------------------------- 货架
def _rack(row_index, row_y, lod):
    P = palette()
    objs = []
    x0 = -RACK_LEN / 2
    seg = 16 if lod == "hi" else 8

    frames = Part(f"Rack_{row_index:02d}_Frames", P["blue"])
    ties = Part(f"Rack_{row_index:02d}_Ties", P["galv"])
    beams = Part(f"Rack_{row_index:02d}_Beams", P["orange"])
    decks = Part(f"Rack_{row_index:02d}_Decks", P["deck"])

    for i in range(COLS + 1):
        x = x0 + i * BAY
        for sy in (-1, 1):
            frames.box((0.10, 0.09, RACK_H), (x, row_y + sy * SIDE_OFF, RACK_H / 2))
        for tz in (0.45, 4.25, 8.55):
            ties.box((0.06, 1.10, 0.06), (x, row_y, tz))
        # 底部调节脚
        for sy in (-1, 1):
            frames.box((0.20, 0.19, 0.05), (x, row_y + sy * SIDE_OFF, 0.025))

    for lv in LEVELS:
        for sy in (-1, 1):
            beams.box((RACK_LEN + 0.14, 0.05, 0.13), (0, row_y + sy * SIDE_OFF, lv))
            if lod == "hi":
                decks.box((RACK_LEN, 1.05, 0.03), (0, row_y + sy * SIDE_OFF, lv + 0.08))

    objs.append(frames.build())
    objs.append(ties.build())
    objs.append(beams.build())
    if lod == "hi":
        objs.append(decks.build())

    # 货位锚点：每跨每层每面
    for ci in range(COLS):
        sx = x0 + (ci + 0.5) * BAY
        for li, lv in enumerate(LEVELS, start=1):
            for si, sy in enumerate((-1, 1), start=1):
                objs.append(
                    add_empty(
                        f"Anchor_Slot_R{row_index:02d}C{ci + 1:02d}L{li}S{si}",
                        (sx, row_y + sy * SIDE_OFF, lv + 0.10),
                    )
                )

    objs.append(add_empty(f"Anchor_Rack_{row_index:02d}", (0, row_y, RACK_H + 1.2)))
    return objs


# ---------------------------------------------------------------- 设备与陈设
def _equipment(lod):
    P = palette()
    seg = 20 if lod == "hi" else 10
    objs = []

    # 后墙冷风机（蒸发器）
    body = Part("Device_Cooler_Body", P["white"])
    fans = Part("Device_Cooler_Fans", P["steel_dark"])
    grille = Part("Device_Cooler_Grille", P["galv"])
    for cx in (-16.0, 0.0, 16.0):
        body.box((4.2, 0.85, 1.5), (cx, ROOM[1] / 2 - 0.75, 8.4))
        for fx in (-1.25, 1.25):
            fans.cyl(0.55, 0.16, (cx + fx, ROOM[1] / 2 - 1.22, 8.4), rot=(math.pi / 2, 0, 0), seg=seg)
        grille.box((3.6, 0.05, 0.06), (cx, ROOM[1] / 2 - 1.30, 7.80))
        grille.box((3.6, 0.05, 0.06), (cx, ROOM[1] / 2 - 1.30, 9.00))
    objs.append(body.build())
    objs.append(fans.build(smooth=True))
    objs.append(grille.build())

    # 顶部灯带
    lights = Part("Device_CeilingLights", P["warm"])
    for ly in (-12.0, -6.0, 0.0, 6.0, 12.0):
        lights.box((RACK_LEN + 2.0, 0.22, 0.10), (0, ly, ROOM[2] - 1.15))
    objs.append(lights.build())

    # 温度监测点
    sensors = Part("Device_TempSensors", P["cyan"])
    for sx in (-18.0, 0.0, 18.0):
        sensors.box((0.22, 0.18, 0.12), (sx, ROOM[1] / 2 - 0.36, 5.4))
    objs.append(sensors.build())

    # 前场作业区：几箱待入库
    for i, (px, py, yaw) in enumerate(
        [(-20.0, -16.0, 0.0), (-18.6, -14.4, 0.0), (18.0, -16.2, 90.0), (19.6, -14.6, 90.0)]
    ):
        objs.extend(build_props.coldbox(f"Stage{i + 1:02d}", (px, py, 0.0), yaw, lod))

    # 前墙月台门（内视）
    for dx in (-9.0, 9.0):
        objs.extend(build_props.dock(f"RoomDoor{1 if dx < 0 else 2:02d}", (dx, -ROOM[1] / 2, 0.0), lod))

    objs.append(add_empty("Anchor_ColdRoom", (0, 0, ROOM[2] + 3.0)))
    return objs


def build(lod="hi"):
    palette()
    objs = []
    objs.extend(_shell(lod))
    for i, ry in enumerate(ROWS, start=1):
        objs.extend(_rack(i, ry, lod))
    objs.extend(_equipment(lod))

    if lod == "hi":
        for ob in objs:
            if ob.type == "MESH" and ob.name.startswith("Rack_") and "Frames" in ob.name:
                bevel(ob, 0.012, 1)
    return objs
