# 3D 模型资源目录

本目录的模型由 Blender 脚本程序化建模并导出（`assets/blender/run_all.py`），
全部为米制、Y 轴朝上，保留业务层级命名，供大屏「园区 → 货位 → 设备」三级下钻使用。

## 模型清单（双档）

| 文件名 | 面数 | 体积 | 尺寸(米) | 说明 |
|---|---|---|---|---|
| `park_hi.glb` / `park_lite.glb` | 31,448 / 7,800 | 1.6MB / 0.4MB | 200 × 160 × 14.4 | 园区：两栋冷库、常温仓、月台、卡车、围界 |
| `coldroom_hi.glb` / `coldroom_lite.glb` | 31,816 / 13,032 | 1.8MB / 0.76MB | 54 × 41.4 × 12.2 | 冷库内部：6 排 × 18 跨 × 3 层货架、648 个货位锚点 |
| `coldbox_hi.glb` / `coldbox_lite.glb` | 772 / 300 | 50KB / 24KB | 1.27 × 1.69 × 1.07 | 冷链箱：货位状态着色对象 |
| `truck_hi.glb` / `truck_lite.glb` | 4,040 / 980 | 182KB / 41KB | 12.35 × 3.93 × 3.1 | 9.6m 冷藏车 |
| `dock_hi.glb` / `dock_lite.glb` | 732 / 240 | 45KB / 18KB | 5.12 × 4.4 × 3.45 | 月台门与升降平台 |

`manifest.json` 记录每档的面数、字节数、包围盒与命名契约，前端可据此做预算校验。

档位选择：`resolvePerfBudget()` 判定为低配（核数 < 4 或超宽画布）时加载 `_lite`，
否则加载 `_hi`。

## 命名契约

| 前缀 | 含义 | 前端用途 |
|---|---|---|
| `Body_` | 状态着色层 | 按节点状态改写 emissive |
| `Device_` | 可点击设备 | 设备级交互 |
| `Anchor_` | 空锚点（Empty） | HTML 铭牌与节点定位 |

锚点命名：

- 楼栋：`Anchor_Building_01`、`Anchor_Building_02`、`Anchor_Ambient`
- 货位：`Anchor_Slot_R{排:02d}C{列:02d}L{层}S{面}`，共 648 个
- 货架：`Anchor_Rack_01..06`
- 库房：`Anchor_ColdRoom`

前端从 `twin_nodes.transform.anchor` 读取锚点名，在加载后的 GLB 中按名称取世界坐标；
锚点不存在时回退到 `transform.x / y / z`。

## 坐标约定

- Blender 导出开启 `export_yup=True`：Blender `+Y` 对应 Three.js `−Z`
- GLB 内部坐标即 Three.js 世界坐标，模型原点位于场景中心
- 园区地块 200 × 160m，冷库 72 × 48 × 12m，货架立柱 9m、跨 2.7m、单面进深 1.1m

## 模型根路径

通过环境变量 `VITE_3D_MODEL_BASE` 覆盖，默认 `/models`。

## 旧版演示模型（保留但大屏不再使用）

`warehouse.glb`、`cold_box.glb`、`shelf.glb`、`vehicle.glb`、`equipment.glb`
为早期 `ColdStorageScene` 的程序化演示模型；孪生舞台现在只使用上表的双档资产。

## 缺失时行为

模型文件缺失时，孪生舞台会保留节点铭牌与点击区域并打印加载错误，
不会导致三维区域白屏。
