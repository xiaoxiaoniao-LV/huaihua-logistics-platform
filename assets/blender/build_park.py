"""L1 园区：地块、道路、两栋冷库、常温仓、月台、车辆、灯杆。

真实尺度参考：单栋冷库 72×48×12m，柱网 12m；月台门 3.4×3.8m；园区地块 200×160m。
"""

import math

import bpy

from bl_common import Part, add_empty, bevel, palette
import build_props


def _ribs(part, axis, start, end, fixed, z0, z1, step, size, offset):
    """在墙面上均匀排布竖向波纹肋。axis='x' 表示沿 X 排布、墙面法线为 Y。"""
    n = max(2, int((end - start) / step))
    span = end - start
    for i in range(n + 1):
        p = start + span * i / n
        if axis == "x":
            part.box(size, (p, fixed + offset, (z0 + z1) / 2))
        else:
            part.box(size, (fixed + offset, p, (z0 + z1) / 2))


def _wall(part, center, size, lod, door_xs=(), door_w=3.4, door_h=3.8, ribs=None):
    """四面墙 + 波纹肋；南墙（-Y）按门洞分段。"""
    W, D, H = size
    cx, cy = center
    t = 0.30
    s = 1.2 if lod == "hi" else 2.4
    ribs = ribs if ribs is not None else (lod == "hi")

    # 北 / 东 / 西
    part.box((W, t, H), (cx, cy + D / 2 - t / 2, H / 2))
    part.box((t, D, H), (cx - W / 2 + t / 2, cy, H / 2))
    part.box((t, D, H), (cx + W / 2 - t / 2, cy, H / 2))

    # 南墙：按门洞切段
    segments = []
    if door_xs:
        edges = []
        for dx in sorted(door_xs):
            edges.append((dx - door_w / 2, dx + door_w / 2))
        cur = cx - W / 2
        for a, b in edges:
            if a > cur:
                segments.append((cur, a))
            cur = max(cur, b)
        if cur < cx + W / 2:
            segments.append((cur, cx + W / 2))
    else:
        segments.append((cx - W / 2, cx + W / 2))

    y_front = cy - D / 2 + t / 2
    for a, b in segments:
        if b - a > 0.05:
            part.box((b - a, t, H), ((a + b) / 2, y_front, H / 2))
    # 门洞上方过梁
    if door_xs:
        for dx in door_xs:
            part.box((door_w, t, H - door_h), (cx + dx, y_front, (H + door_h) / 2))

    if ribs:
        y_rib = cy - D / 2 + 0.02
        x0, x1 = cx - W / 2 + 0.4, cx + W / 2 - 0.4
        for i in range(int((x1 - x0) / s) + 1):
            px = x0 + i * s
            if any(abs(px - (cx + dx)) < door_w / 2 + 0.1 for dx in door_xs):
                continue
            part.box((0.07, 0.09, H - 0.4), (px, y_rib - 0.09, H / 2))
        y_back = cy + D / 2 - 0.02
        for i in range(int((x1 - x0) / s) + 1):
            px = x0 + i * s
            part.box((0.07, 0.09, H - 0.4), (px, y_back + 0.09, H / 2))
        z_rib = H - 0.3
        for side in (-1, 1):
            x_side = cx + side * (W / 2 - 0.02)
            y0, y1 = cy - D / 2 + 0.4, cy + D / 2 - 0.4
            for i in range(int((y1 - y0) / s) + 1):
                py = y0 + i * s
                part.box((0.09, 0.07, H - 0.4), (x_side + side * 0.09, py, z_rib / 2 + 0.2))


def _cold_building(name, center, size, lod, door_xs, status_index):
    P = palette()
    W, D, H = size
    cx, cy = center
    objs = []

    walls = Part(f"Shell_Walls_{name}", P["steel"])
    _wall(walls, center, size, lod, door_xs=door_xs)
    objs.append(walls.build())

    roof = Part(f"Shell_Roof_{name}", P["steel_dark"])
    roof.box((W + 0.8, D + 0.8, 0.35), (cx, cy, H + 0.175))
    # 女儿墙
    pw, ph = 0.25, 1.1
    roof.box((W + 0.8, pw, ph), (cx, cy - D / 2 - 0.4 + pw / 2, H + 0.35 + ph / 2))
    roof.box((W + 0.8, pw, ph), (cx, cy + D / 2 + 0.4 - pw / 2, H + 0.35 + ph / 2))
    roof.box((pw, D + 0.8, ph), (cx - W / 2 - 0.4 + pw / 2, cy, H + 0.35 + ph / 2))
    roof.box((pw, D + 0.8, ph), (cx + W / 2 + 0.4 - pw / 2, cy, H + 0.35 + ph / 2))
    objs.append(roof.build())

    frame = Part(f"Shell_Frame_{name}", P["galv"])
    # 角柱与中间柱
    xs = [cx - W / 2 + 0.35, cx + W / 2 - 0.35]
    x = cx - W / 2 + 12
    while x < cx + W / 2 - 1:
        xs.append(x)
        x += 12
    for px in xs:
        for py in (cy - D / 2 + 0.35, cy + D / 2 - 0.35):
            frame.box((0.7, 0.7, H), (px, py, H / 2))
    # 檐口
    frame.box((W + 1.0, 0.35, 0.45), (cx, cy - D / 2 - 0.42, H - 0.1))
    objs.append(frame.build())

    # 月台雨棚
    canopy = Part(f"Shell_Canopy_{name}", P["steel_dark"])
    canopy.box((W + 6, 6.5, 0.28), (cx, cy - D / 2 - 3.4, 8.4))
    canopy.box((W + 6, 0.18, 0.9), (cx, cy - D / 2 - 6.6, 8.9))
    objs.append(canopy.build())

    # 屋顶制冷机组
    units = Part(f"Device_RoofUnits_{name}", P["white"])
    fans = Part(f"Device_RoofFans_{name}", P["steel_dark"])
    for dx in (-W / 4, W / 4):
        ux, uy, uz = cx + dx, cy, H + 0.35
        units.box((3.4, 1.8, 1.6), (ux, uy, uz + 0.8))
        fans.cyl(0.55, 0.16, (ux - 0.75, uy, uz + 1.68), seg=24 if lod == "hi" else 12)
        fans.cyl(0.55, 0.16, (ux + 0.75, uy, uz + 1.68), seg=24 if lod == "hi" else 12)
    objs.append(units.build())
    objs.append(fans.build(smooth=True))

    # 状态光带（前端按状态着色）
    band = Part(f"Body_Status_{status_index:02d}", P["body"])
    band.box((W - 2.0, 0.10, 0.34), (cx, cy - D / 2 - 0.52, H - 1.4))
    objs.append(band.build())

    # 月台门
    for i, dx in enumerate(door_xs, start=1):
        objs.extend(
            build_props.dock(
                f"{name}_Dock{i:02d}",
                (cx + dx, cy - D / 2, 0.0),
                lod,
            )
        )

    objs.append(add_empty(f"Anchor_Building_{status_index:02d}", (cx, cy, H + 4.0)))
    return objs


def _ambient_building(name, center, size, lod):
    P = palette()
    W, D, H = size
    cx, cy = center
    objs = []
    walls = Part(f"Shell_Walls_{name}", P["white"])
    _wall(walls, center, size, lod, door_xs=[-8, 8], door_w=4.0, door_h=4.2)
    objs.append(walls.build())
    roof = Part(f"Shell_Roof_{name}", P["steel_dark"])
    roof.box((W + 0.6, D + 0.6, 0.3), (cx, cy, H + 0.15))
    objs.append(roof.build())
    band = Part(f"Body_Status_{name}", P["body"])
    band.box((W - 2.0, 0.10, 0.30), (cx, cy - D / 2 - 0.5, H - 1.2))
    objs.append(band.build())
    objs.append(add_empty(f"Anchor_{name}", (cx, cy, H + 3.0)))
    return objs


def _ground(lod):
    P = palette()
    objs = []
    g = Part("Ground_Slab", P["concrete"])
    g.box((200, 160, 0.3), (0, 0, -0.15))
    objs.append(g.build())

    road = Part("Ground_Road", P["asphalt"])
    road.box((200, 12, 0.06), (0, -14, 0.03))
    road.box((12, 34, 0.06), (0, -46, 0.03))
    objs.append(road.build())

    apron = Part("Ground_Apron", P["concrete"])
    apron.box((168, 14, 0.10), (0, 0, 0.05))
    objs.append(apron.build())

    # 标线
    line = Part("Ground_Markings", P["yellow"])
    for x in range(-96, 97, 8):
        line.box((3.0, 0.14, 0.02), (x, -14, 0.08))
    for y in range(-60, -28, 8):
        line.box((0.14, 3.0, 0.02), (0, y, 0.08))
    # 月台前安全线
    line.box((168, 0.16, 0.02), (0, -7.0, 0.11))
    objs.append(line.build())

    white = Part("Ground_LaneEdge", P["white"])
    white.box((200, 0.12, 0.02), (0, -20, 0.08))
    white.box((200, 0.12, 0.02), (0, -8, 0.08))
    objs.append(white.build())
    return objs


def _gate(lod):
    P = palette()
    objs = []
    box = Part("Shell_GateHouse", P["white"])
    box.box((10, 6, 4.2), (0, -72, 2.1))
    objs.append(box.build())
    roof = Part("Shell_GateRoof", P["steel_dark"])
    roof.box((12, 8, 0.4), (0, -72, 4.4))
    objs.append(roof.build())
    win = Part("Device_GateWindow", P["glass"])
    win.box((3.6, 0.12, 1.4), (0, -69.05, 2.8))
    objs.append(win.build())
    arm = Part("Device_GateBarrier", P["orange"])
    arm.box((0.24, 7.0, 0.24), (5.5, -66.5, 1.1))
    objs.append(arm.build())
    return objs


def _lights(lod):
    P = palette()
    objs = []
    pole = Part("Shell_LightPoles", P["steel_dark"])
    head = Part("Device_LightHeads", P["cyan"])
    for x in (-70, -24, 24, 70):
        pole.cyl(0.16, 10.0, (x, -4.0, 5.0), seg=16 if lod == "hi" else 8)
        pole.box((2.4, 0.16, 0.16), (x - 1.2, -4.0, 9.9))
        head.box((1.2, 0.5, 0.16), (x - 2.3, -4.0, 9.8))
    objs.append(pole.build(smooth=True))
    objs.append(head.build())
    return objs


def _fence(lod):
    """园区围界：沿地块边界布立柱，南侧留出入口；hi 档补两道横杆。"""
    P = palette()
    posts = Part("Site_FencePosts", P["steel_dark"])
    rails = Part("Site_FenceRails", P["steel_dark"])

    for x in range(-96, 97, 8):
        for y in (-79.0, 79.0):
            if y < 0 and -9 <= x <= 9:
                continue
            posts.box((0.12, 0.12, 2.2), (x, y, 1.1))
    for y in range(-72, 73, 8):
        for x in (-99.0, 99.0):
            posts.box((0.12, 0.12, 2.2), (x, y, 1.1))

    if lod == "hi":
        for z in (1.05, 1.85):
            rails.box((198, 0.06, 0.07), (0, 79.0, z))
            rails.box((90, 0.06, 0.07), (-54.0, -79.0, z))
            rails.box((90, 0.06, 0.07), (54.0, -79.0, z))
            rails.box((0.06, 158, 0.07), (-99.0, 0, z))
            rails.box((0.06, 158, 0.07), (99.0, 0, z))

    objs = [posts.build()]
    if lod == "hi":
        objs.append(rails.build())
    return objs


def _yard_goods(lod):
    """月台前待运冷链箱，给园区一个可判断尺度的参照。"""
    objs = []
    spots = [
        (32.2, 1.4, 0.0),
        (33.5, 1.4, 0.0),
        (34.8, 1.4, 0.0),
        (32.2, 2.9, 90.0),
        (-24.0, 1.2, 0.0),
        (-22.7, 1.2, 0.0),
    ]
    if lod == "lite":
        spots = spots[:3]
    for i, (px, py, yaw) in enumerate(spots, start=1):
        objs.extend(build_props.coldbox(f"YardBox{i:02d}", (px, py, 0.0), yaw, lod))
    return objs


def build(lod="hi"):
    palette()
    objs = []
    objs.extend(_ground(lod))
    objs.extend(_fence(lod))
    objs.extend(
        _cold_building("ColdA", (-45, 30), (72, 48, 12), lod, [-27, -9, 9, 27], 1)
    )
    objs.extend(
        _cold_building("ColdB", (45, 30), (72, 48, 12), lod, [-27, -9, 9, 27], 2)
    )
    objs.extend(_ambient_building("Ambient", (0, -42), (54, 32, 10), lod))
    objs.extend(_gate(lod))
    objs.extend(_lights(lod))

    # 两台车：1 号库月台倒车靠台，2 号车在园区主路
    objs.extend(build_props.truck("Truck01", (-54, 0.9, 0.0), -90.0, lod))
    objs.extend(build_props.truck("Truck02", (40, -14.0, 0.0), 180.0, lod))
    objs.extend(_yard_goods(lod))

    if lod == "hi":
        for ob in objs:
            if ob.type == "MESH" and any(
                k in ob.name for k in ("Frame_", "GateHouse", "GateRoof")
            ):
                bevel(ob, 0.03, 2)
    return objs
