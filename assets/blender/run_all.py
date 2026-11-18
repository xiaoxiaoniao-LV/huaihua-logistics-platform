"""批量构建 / 导出 / 统计 / 预览。

用法：
    blender -b --python run_all.py
    blender -b --python run_all.py -- --only park --lod hi

输出：
    frontend-vue/public/models/{park,coldroom,truck,coldbox,dock}_{hi,lite}.glb
    frontend-vue/public/models/manifest.json
    assets/previews/*.png
"""

import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import bl_common as C  # noqa: E402
import build_park  # noqa: E402
import build_coldroom  # noqa: E402
import build_props  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "frontend-vue", "public", "models")
PRE = os.path.join(ROOT, "assets", "previews")

ASSETS = ["park", "coldroom", "truck", "coldbox", "dock"]
LODS = ["hi", "lite"]

# 预览机位：相机方向（从目标指向相机）+ 焦距；距离由包围盒自动计算
VIEWS = {
    "park": ((0.72, -1.0, 0.58), 45.0),
    "coldroom": ((0.05, -1.0, 0.62), 40.0),
    "truck": ((0.90, -1.0, 0.48), 55.0),
    "coldbox": ((0.70, 1.00, 0.62), 60.0),
    "dock": ((0.55, -1.0, 0.42), 55.0),
}

ENGINE = os.environ.get("BL_ENGINE", "BLENDER_EEVEE_NEXT")


def _argv():
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def _build(asset, lod):
    C.reset()
    if asset == "park":
        return build_park.build(lod)
    if asset == "coldroom":
        return build_coldroom.build(lod)
    if asset == "truck":
        return build_props.truck("Truck01", (0.0, 0.0, 0.0), 0.0, lod)
    if asset == "coldbox":
        return build_props.coldbox("ColdBox01", (0.0, 0.0, 0.0), 0.0, lod)
    if asset == "dock":
        return build_props.dock("Dock01", (0.0, 0.0, 0.0), lod)
    raise ValueError(asset)


def _clear_rig():
    for ob in list(bpy.data.objects):
        if ob.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(ob, do_unlink=True)


def _preview(asset, objs, path):
    global ENGINE
    direction, lens = VIEWS[asset]
    size, mn, mx = C.world_bbox(objs)
    center = tuple((mn[i] + mx[i]) / 2.0 for i in range(3))
    radius = max(0.6, 0.5 * max(size))
    res = (1400, 788)

    C.setup_studio(engine=ENGINE, center=center, radius=radius, direction=direction)
    C.frame_camera(objs, direction, lens, res)
    try:
        return C.render_to(path, res)
    except Exception as exc:  # 无 GPU / EEVEE 不可用 → 退回 Cycles CPU
        print(f"[preview] {ENGINE} 失败：{exc}", flush=True)
        if ENGINE == "CYCLES":
            raise
        ENGINE = "CYCLES"
        _clear_rig()
        C.setup_studio(engine="CYCLES", center=center, radius=radius, direction=direction)
        C.frame_camera(objs, direction, lens, res)
        return C.render_to(path, res)


def main():
    args = _argv()
    only = None
    lods = LODS
    for i, a in enumerate(args):
        if a == "--only" and i + 1 < len(args):
            only = args[i + 1].split(",")
        if a == "--lod" and i + 1 < len(args):
            lods = args[i + 1].split(",")
    assets = [a for a in ASSETS if not only or a in only]

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PRE, exist_ok=True)

    manifest = {
        "version": 1,
        "units": "meter",
        "up_axis": "Y",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "naming": {
            "Body_": "状态着色层（前端按业务状态改色）",
            "Device_": "可点击设备节点",
            "Anchor_": "空锚点，供 HTML 标签挂载",
            "Slot_": "货位锚点（Anchor_Slot_RxxCxxLxSx）",
        },
        "assets": {},
    }

    failures = []
    for asset in assets:
        manifest["assets"][asset] = {}
        for lod in lods:
            tag = f"{asset}_{lod}"
            t0 = time.time()
            try:
                objs = _build(asset, lod)
                tris = C.tri_count(objs)
                size, mn, mx = C.world_bbox(objs)
                path = os.path.join(OUT, f"{tag}.glb")
                nbytes = C.export_glb(path, objs)
                entry = {
                    "file": f"{tag}.glb",
                    "triangles": tris,
                    "bytes": nbytes,
                    "objects": len(objs),
                    "size": size,
                    "min": mn,
                    "max": mx,
                }
                manifest["assets"][asset][lod] = entry
                print(
                    f"OK  {tag:<14} tri={tris:<7} "
                    f"size={size[0]}x{size[1]}x{size[2]}  "
                    f"glb={nbytes / 1024:.0f}KB  {time.time() - t0:.1f}s",
                    flush=True,
                )
                if lod == "hi":
                    img = os.path.join(PRE, f"{tag}.png")
                    pbytes = _preview(asset, objs, img)
                    print(f"IMG {tag:<14} {pbytes / 1024:.0f}KB  {img}", flush=True)
            except Exception:
                failures.append(tag)
                print(f"FAIL {tag}", flush=True)
                traceback.print_exc()

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"MANIFEST {os.path.join(OUT, 'manifest.json')}", flush=True)

    total_hi = sum(v["hi"]["bytes"] for v in manifest["assets"].values() if "hi" in v)
    total_lite = sum(v["lite"]["bytes"] for v in manifest["assets"].values() if "lite" in v)
    print(f"TOTAL hi={total_hi / 1024:.0f}KB lite={total_lite / 1024:.0f}KB", flush=True)
    print("FAILURES " + (", ".join(failures) if failures else "none"), flush=True)


main()
