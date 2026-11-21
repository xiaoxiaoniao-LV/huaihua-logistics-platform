# 硬件阶段执行 SOP（采购 → 接线 → 刷机 → 实机验收）

> 适用前提：软件侧已全部就绪（起栈、演示账号、设备预配、固件签名发布）。
> 本 SOP 覆盖从「下单买物料」到「三段实机验收通过」的全部现场操作，可打印照着打勾。
> 详细原理与排障参考 [固件 README](../iot/firmware/README.md) 与 [部署运维说明](./部署运维说明.md)。

---

## 一、前置状态检查（10 分钟，全绿才开工）

在平台服务器上执行：

```powershell
docker compose ps                # 期望：6 个容器全部 healthy / running
python scripts/smoke.py          # 期望：全部 PASS（可跳过登录项）
python scripts/acceptance.py     # 期望：12/12 通过（无硬件虚拟验收）
```

再核对三件事：

- [ ] 节点配置已生成：`iot/firmware/nodes/CW-01|TR-01|GW-01/config.py` 三个目录都在
- [ ] `.env` 中 `DEVICE_INGEST_TOKEN`、`OTA_PUBLIC_KEY`、`OTA_REQUIRE_SIGNATURE=true` 已配置
- [ ] 固件发布包存在：`iot/firmware/releases/3.1.0/`（manifest.json 含 signature）

### 现场工具清单（采购物料之外要备的）

| 工具 | 用途 |
|---|---|
| 电脑（Win/Mac/Linux） | 装 Thonny（MicroPython 上传）或 esptool |
| Micro-USB / USB-C 数据线 ×1 | 烧录（要数据线，不要纯充电线） |
| 万用表 ×1 | 接线检查（通断/电压） |
| 镊子 + 剪刀 | 杜邦线整理、门磁引线剥皮 |
| 热风枪/吹风机 | 演练 C 制造越限热源 |
| 保温箱 + 冰袋（实验室现成） | 模拟冷库/冷藏车环境 |

---

## 二、采购下单清单（照着买即可）

### 本期必买（合计约 150~250 元，不含运费）

| # | 物料 | 精确规格 | 数量 | 参考价 | 购买注意 |
|---|---|---|---|---|---|
| 1 | ESP32 开发板 | ESP32 DevKit V1，板载 CH340 或 CP2102 串口芯片 | 3 | 25~35 元/块 | 认准「DevKit V1 38 脚」；带 USB-C 口更好 |
| 2 | 温湿度模块 | DHT22 / AM2302，模块板（自带 10kΩ 上拉） | 2 | 8~15 元 | 不要买成 DHT11（精度不够）；量程 -40~80℃ |
| 3 | 门磁 | 常闭型干簧管门磁，带引出线 | 2 | 3~8 元 | 必须是「常闭」（磁铁靠近吸合导通）；选带线的 |
| 4 | 六轴 IMU | MPU6050 模块（GY-521） | 1 | 5~10 元 | I2C 地址 0x68 |
| 5 | 电流/功率 | INA219 模块（板载 0.1Ω 采样电阻） | 1 | 8~15 元 | I2C 地址 0x40 |
| 6 | 面包板 + 杜邦线 | 400 孔面包板 + 杜邦线三扎（公对公/公对母/母对母） | 2 套 | 15~25 元/套 | 杜邦线买 10cm 即可 |
| 7 | USB 电源 | 5V/1A 电源适配器 + 数据线 | 3 | 10~20 元/套 | ESP32 供电口与烧录口同一个，用适配器长期供电 |

> 渠道：淘宝/立创商城均可；全部是通用电子料，无需指定品牌。
> 保温箱 + 冰袋不采购，用实验室现成即可。

### 现场部署时再买（多机/港区试点阶段）

| 物料 | 规格 | 用途 |
|---|---|---|
| 工控机或服务器 | ≥4 核 8G，装 Docker | 替代开发机 7×24 跑平台 |
| UPS | 500VA 以上 | 断电续航 |
| 4G/专线路由 + 交换机 | 支持 2.4GHz WiFi 或有线 | 港区网络回传 |

### 二期可选（本期不买，避免重复）

NEO-6M GPS（车载轨迹）、0.96" OLED（现场读数）、BH1750（光照）、LoRa SX1278 ×2（远距离回传）。

---

## 三、到货 QC（10 分钟）

| 物料 | 检查点 |
|---|---|
| ESP32 | 上电后串口 115200 能打印启动日志；板载 LED 亮 |
| DHT22 | 看引脚丝印：VCC / DATA / GND 三脚齐全，模块板上有上拉电阻（标 472/103） |
| 门磁 | 万用表蜂鸣档：磁铁靠近导通、移开断开（常闭型） |
| MPU6050 | 板面印 GY-521，VCC/GND/SDA/SCL 四脚齐全 |
| INA219 | 板面有 0.1Ω 采样电阻（印 R100 或 0R1），VIN+/VIN- 端子 |

---

## 四、烧录与上传文件（每块板约 10 分钟）

### 4.1 刷 MicroPython

1. 电脑安装 **Thonny**（thonny.org，免费）。
2. USB 数据线连接 ESP32，Thonny 右下角选择解释器：`MicroPython (ESP32)` 或对应串口（COMx）。
3. 若板内无 MicroPython：Thonny → 工具 → 选项 → 解释器 → `安装或更新 MicroPython`，选 **ESP32 通用版 v1.22+**，点击安装。
4. 验证：Thonny Shell 里输入 `print("ok")` 有回显。

### 4.2 上传文件

每块板需要 4 个文件（从仓库拷贝到板子根目录 `/`）：

| 文件 | 来源路径 | 说明 |
|---|---|---|
| `main.py` | `iot/firmware/main.py` | 固件主程序（三节点同一份） |
| `ota.py` | `iot/firmware/ota.py` | 文件级 OTA 执行器 |
| `ed25519.py` | `iot/firmware/ed25519.py` | 清单验签 |
| `config.py` | `iot/firmware/nodes/<节点编码>/config.py` | **每块板拷自己目录的那份** |
| `umqtt/simple.py`（可选） | microPython-lib 仓库取 `umqtt/simple.py` | 仅需 MQTT 下行 OTA；缺失自动降级纯 HTTP |

> 要点：`config.py` / `boot.py` 永不参与 OTA 分发——节点身份、WiFi、令牌都在本地，
> 升级时不会被覆盖。目录结构必须是 `/umqtt/simple.py`。

### 4.3 上传后必须改的两处（每个节点）

用 Thonny 打开板内 `config.py` 修改，保存到板子：

```python
WIFI_SSID = "现场2.4GHz的WiFi名"      # 当前是占位值 your-wifi-ssid
WIFI_PASSWORD = "WiFi密码"            # 当前是占位值 your-wifi-password
```

- ESP32 只支持 **2.4GHz**，不支持 5GHz。
- `HTTP_BASE`（当前 `http://10.136.155.233:8080`）与 `MQTT_HOST`（`10.136.155.233`）已按预配时
  探测的平台 IP 写入；若现场平台换了 IP/端口，同步改这两项。
- `DEVICE_TOKEN`、`OTA_PUBLIC_KEY`、`OTA_ALLOW_UNSIGNED=False` 已写入，**不要动**。
- 运输节点 TR-01 接好 MPU6050/INA219 后，把 `ENABLE_MPU6050`、`ENABLE_INA219` 改为 `True`。

---

## 五、分节点接线（约 30 分钟）

### 5.1 三块板公共部分

| 器件 | 引脚 | ESP32 | 固件常量 |
|---|---|---|---|
| 板载 LED | — | GPIO2 | `LED_PIN = 2`（无需接） |
| DHT22 | VCC / DATA / GND | 3V3 / GPIO4 / GND | `DHT_PIN = 4` |
| 门磁 | 一端 / 另一端 | GPIO5 / GND | `DOOR_PIN = 5`（内部上拉，无需电阻） |

### 5.2 冷库节点 CW-01（ROLE = cold）

只接 DHT22 + 门磁：DHT22 放保温箱内测 `temp_in`，门磁贴在箱盖开合处。

### 5.3 运输节点 TR-01（ROLE = trans）

DHT22 + 门磁，另外 I2C 总线并联两颗传感器：

| 器件 | SDA | SCL | VCC / GND |
|---|---|---|---|
| MPU6050 / INA219 | GPIO21 | GPIO22 | 3V3 / GND |

接好线后把 `config.py` 的 `ENABLE_MPU6050`、`ENABLE_INA219` 改成 `True`。

### 5.4 网关节点 GW-01（ROLE = gateway）

只接板载 LED（自身上报 `rssi`），承担 ESP-NOW 汇聚与 MQTT 下行 OTA。

### 5.5 安全红线（上电前逐条打勾）

- [ ] 所有器件共地，统一 3.3V 供电；**GPIO 不耐 5V**，没接任何 5V 到信号脚
- [ ] DHT22 的 DATA 与 VCC 之间有上拉（模块板内置则跳过）
- [ ] 门磁只接 GPIO5 与 GND，无外接电阻
- [ ] 面包板无明显短路（上电前万用表量 3V3 与 GND 之间不通）

---

## 六、上电与平台侧验证（20 分钟）

### 6.1 上电顺序

1. 三块板接 USB 电源，Thonny 或串口工具（115200）观察每块板，预期依次出现：

```
[CW-01] 角色 cold 就绪：dht=True door=True mpu=False ina=False
[CW-01] WiFi 已连接: 192.168.x.x
[CW-01] NTP 对时成功
[CW-01] 补传成功 4 条，剩余 0
```

2. 若有 `HTTP 上报异常` 或 WiFi 连不上：见第九节排查。

### 6.2 平台侧验证（在服务器上执行）

```powershell
# 三台设备都应出现且 status=online（当前共 39 台：36 演示 + CW-01/TR-01/GW-01）
python -c "import sys; sys.path.insert(0,'scripts'); from _flow import http_json; d=http_json('http://127.0.0.1:8010','GET','/api/v1/devices'); [print(x.get('device_code'), x.get('status')) for x in d[1] if x.get('device_code') in ('CW-01','TR-01','GW-01')]"

# 单台点位与新鲜度（换成 CW-01 / TR-01 / GW-01 各查一次）
curl http://127.0.0.1:8010/api/v1/iot/devices/CW-01/state
curl http://127.0.0.1:8010/api/v1/iot/devices/CW-01/points
curl "http://127.0.0.1:8010/api/v1/iot/devices/CW-01/events?limit=10"
```

浏览器确认：大屏 `http://<平台IP>:8080` 与设备面板能看到三节点实时数据与 WebSocket 推送。

---

## 七、三段实机验收（约 1~2 小时，照着打勾）

### 演练 A：断网补传

1. [ ] 设备正常运行，串口出现 `补传成功 … 剩余 0`
2. [ ] 关闭现场 2.4GHz WiFi（或拔路由网线）约 **2 分钟**（≥6 条采样）
3. [ ] 串口出现 `HTTP 上报异常` 并持续打印缓存条数；平台设备状态约 90 秒后转 `offline`
4. [ ] 恢复网络，串口出现 `补传成功 N 条`，N 与离线期间采样数一致
5. [ ] 平台验证：`/events` 时间戳连续；`/state` 的 `last_seen_at` 追上当前时间

**验收标准**：一次断网补传，离线期间数据无缺口；重复补传时平台 `duplicates` 递增而 `accepted` 为 0。

### 演练 B：门磁开合

1. [ ] 保持门关闭，`/state` 中 `door=false`
2. [ ] 打开保温箱盖（或冷库门），1~2 个采样内 `/state` 变 `door=true`，`/events` 新增 `door_open`（warn）
3. [ ] 关门后新增 `door_close`（info）
4. [ ] CW-01 与 TR-01 各做一次，验证多设备互不干扰

**验收标准**：一次开合恰好产生一条开启 + 一条关闭，不重复、不抖动。

### 演练 C：越限与恢复

1. [ ] 用吹风机/暖手宝靠近 DHT22，使 `temp_in`（或 `temp_supply`）升到 -5℃ 以上
2. [ ] 连续 3 个采样越限后：`/events` 出现 `alarm_temp_in_high`，`/alerts` 出现 `temp_in_high`（critical）
3. [ ] 撤掉热源，温度回到 -18℃ 后：事件 `resolved_at` 被填写，告警状态变 `resolved`
4. [ ] 反例验证：只越限 1~2 个采样不告警（去抖生效）

**验收标准**：连续 3 次越限必告警、回到区间立即自动恢复、1~2 次越限不误报。

### 演练 D：运输振动与电流（MPU6050 / INA219，TR-01）

1. [ ] 静止放置 TR-01，`/state` 的 `vibration` 接近 0
2. [ ] 轻晃面包板，`vibration` 明显上升；`current_a` 随负载变化
3. [ ] 只验证采集与上报，不做阈值判定

---

## 八、验收记录与放行表

| # | 检查项 | 标准 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 三节点上线 | CW-01 / TR-01 / GW-01 均 `online` | | |
| 2 | 演练 A 断网补传 | 离线数据无缺口、重放零重复 | | |
| 3 | 演练 B 门磁开合 | 开/关事件各一条，无抖动 | | |
| 4 | 演练 C 越限恢复 | 3 次告警、恢复自动、1~2 次不误报 | | |
| 5 | 演练 D 振动电流 | 数值随动作变化 | | |
| 6 | 大屏/面板实时 | WebSocket 推送无需刷新 | | |
| 7 | OTA 拉取链路 | `GET /api/v1/devices/ota/manifest/3.1.0`（带 `X-Device-Token`）返回 200 | | |

全部打勾后：**硬件阶段验收通过**，可进入港区试点部署（现场服务器 / 网络 / 多机接入，见 [部署运维说明](./部署运维说明.md) 第十四节）。

---

## 九、常见问题快速排查

| 现象 | 排查 |
|---|---|
| 串口无输出 | 数据线是否纯充电线；波特率是否 115200；重新按住 BOOT 上电进入烧录模式 |
| WiFi 连不上 | 只支持 2.4GHz；SSID/密码含特殊字符时用引号；距离路由太远 |
| 温度显示 0 或异常 | DHT22 线序错（VCC/DATA/GND）；DATA 与 VCC 间无上拉；采样间隔 <2s |
| 平台看不到设备 | `HTTP_BASE` 指向的平台 IP/端口是否可达；`DEVICE_TOKEN` 是否与 `.env` 一致；串口看上报返回码 |
| 上报 4xx | 点位键不在字典（用内置 `temp_in/temp_supply/hum_in/door/rssi`）；令牌错误返回 401 |
| 门磁事件反了 | 常开/常闭买错：固件按「关门吸合=低电平」设计，需常闭型 |
| OTA 拉清单 401/503 | 设备没带 `X-Device-Token` 或服务端 `DEVICE_INGEST_TOKEN` 未配置（见部署文档 14.3） |
| 串口 `umqtt 缺失` | 不影响 HTTP 上报；需要 MQTT 下行时补传 `umqtt/simple.py` |

---

## 附录：文件与命令速查

```
仓库根目录
├── iot/firmware/main.py            # 三节点同一份固件
├── iot/firmware/ota.py             # OTA 执行器
├── iot/firmware/ed25519.py         # 验签
├── iot/firmware/nodes/<编码>/config.py   # 每节点专属配置（现场只改这个）
└── iot/firmware/releases/3.1.0/    # 已签名发布包

一键命令（服务器上）：
  python scripts/bootstrap.py                    # 起栈（幂等）
  python scripts/acceptance.py                   # 无硬件虚拟验收 12/12
  python scripts/provision_devices.py --release 3.1.0   # 重新签名发布（改了固件后）
```
