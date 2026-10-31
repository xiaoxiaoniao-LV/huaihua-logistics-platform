# 3D 模型资源目录

本目录下的 GLB 模型由 `three.js GLTFExporter` 程序化生成，全部为米制、Y 轴朝上，并保留业务层级命名，供前端「可拆解」交互使用。

## 模型清单

| 文件名 | 尺寸(米) | 说明 |
|---|---|---|
| `warehouse.glb` | 24 × 8 × 16 | 冷链仓库主体：含库区、货架、冷库、月台、设备节点 |
| `cold_box.glb` | 1.6 × 1.2 × 1.2 | 冷链箱：箱体、门、制冷机组、控制面板、传感器 |
| `shelf.glb` | 2.4 × 2.8 × 1.0 | 三层货架 |
| `vehicle.glb` | 8.2 × 3.1 × 2.4 | 冷藏货车：驾驶室、冷藏货箱、制冷机组、车轮 |
| `equipment.glb` | 0.7 × 2.0 × 0.7 | 环境监测站：立杆、传感器头、太阳能板、控制箱 |

## 业务层级命名（拆解依据）

```
warehouse.glb
└── Warehouse
    ├── Structure_Floor / Structure_Wall_* / Structure_Roof
    ├── Dock_Platform / Dock_Door_01 / Dock_Door_02
    ├── Zone_A
    │   ├── Zone_A_Marking
    │   ├── Shelf_A1 / Shelf_A2
    │   └── ColdRoom_A
    │       ├── ColdRoom_A_Wall_Back / _Left / _Right / _Ceiling / _Door
    │       └── CoolingUnit_A / CoolingUnit_A_Fan
    ├── Zone_B（结构同 Zone_A）
    └── Device_SensorHub_01 / Device_SensorHub_02 / Device_TempProbe_ColdA / _ColdB

cold_box.glb
└── ColdBox
    ├── Body          ← 状态着色作用于此节点
    ├── Door / Door_Handle
    ├── CoolingUnit（Housing / Grille / Fan）
    ├── ControlPanel（Face / LED_Temp / LED_Alarm / Screen）
    ├── Sensor_Temperature / Sensor_Humidity
    └── Foot_1 ~ Foot_4
```

前端 `ColdStorageScene` 会遍历模型，把名称以 `Device_` 开头的节点登记为可点击设备（拆解到设备层）。

## 替换为真实模型

如需换成外部真实模型（如 Blender 导出的园区模型），保持同名同层级即可直接替换：

1. 格式 `.glb`，Y 轴朝上，单位为米
2. 主体网格命名以 `Body` 开头（状态着色依赖此命名）
3. 设备节点命名以 `Device_` 开头
4. 建议 Blender 导出时开启 Draco 压缩

模型根路径可通过环境变量 `VITE_3D_MODEL_BASE` 覆盖（默认 `/models`）。

## 缺失时行为

若某个模型文件缺失，场景会自动回退到程序化几何体，功能不受影响。
