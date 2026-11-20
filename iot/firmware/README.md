# 实机接入：三节点 ESP32 传感器组网（实验室复刻港区部署）

P0 硬件链路固定为 **HTTP 窄表上报**：设备每 10 秒向 `POST /api/v1/iot/telemetry` 提交一条
`TelemetryEnvelope`，平台按 `(设备, 点位, 时间戳)` 幂等落库。断网补传、门磁事件、越限去抖都在平台侧闭环。

本期做 **三节点组网**：冷库节点 CW-01、运输节点 TR-01、网关节点 GW-01，用同一份固件靠 `config.py` 的
`ROLE` 切换角色，对应港区真实的"库内监测 + 在途监测 + 边缘汇聚"部署形态。

没有硬件时不必等采购，直接跑 `iot/simulator_http.py` 即可完成同样的三段演练（见第四节）。

## 一、物料（BOM）

ESP32 按节点数买 3 块，其余传感器每种一套即可，不重复采购。

### 本期必买

| 物料 | 数量 | 归属节点 | 说明 |
|---|---|---|---|
| ESP32 DevKit V1 | 3 | CW/TR/GW | 带 WiFi 的 ESP32，MicroPython v1.22+ |
| DHT22 / AM2302 | 2 | CW、TR | 温湿度，量程 -40~80℃；模块板自带 10kΩ 上拉 |
| 常闭型簧片门磁 | 2 | CW、TR | 门关闭时磁簧吸合导通 |
| MPU6050 | 1 | TR | 六轴 IMU，运输振动/倾角 |
| INA219 | 1 | TR | 电流/功率（替代 220V 互感器，实验室更安全） |
| 面包板 + 杜邦线 | 2 套 | 全部 | 3.3V 供电，共地 |
| 5V/1A USB 电源 | 3 | 全部 | 实验室取电 |

### 二期可选（本期先不买，避免重复）

| 物料 | 数量 | 说明 |
|---|---|---|
| NEO-6M GPS | 1 | 车载轨迹上报经纬度（点位 `longitude`/`latitude`） |
| 0.96" OLED（I2C） | 1 | 现场查看节点编号与实时读数，演示加分 |
| BH1750 光照 | 1 | 暂无对应点位，留作扩展 |
| LoRa SX1278 模块 | 2 | 港区远距离回传验证，二期 |

保温箱 + 冰袋用实验室现成的即可，用于模拟冷库/冷藏车环境与越限演练。

## 二、接线

三块板都一样的部分：

| 器件 | 引脚 | ESP32 | 固件常量 |
|---|---|---|---|
| 板载 LED | — | GPIO2 | `LED_PIN = 2` |
| DHT22 | VCC / DATA / GND | 3V3 / GPIO4 / GND | `DHT_PIN = 4` |
| 门磁 | 一端 / 另一端 | GPIO5 / GND | `DOOR_PIN = 5` |

### 冷库节点 CW-01（`ROLE = "cold"`）

只接 DHT22 + 门磁。DHT22 放保温箱内测 `temp_in`，门磁贴在箱盖开合处。

### 运输节点 TR-01（`ROLE = "trans"`）

DHT22 + 门磁，另外 I2C 挂两颗传感器（同一组总线可并联）：

| 器件 | 引脚 | ESP32 | 固件常量 |
|---|---|---|---|
| MPU6050 / INA219 | SDA | GPIO21 | `I2C_SDA = 21` |
| MPU6050 / INA219 | SCL | GPIO22 | `I2C_SCL = 22` |
| MPU6050 / INA219 | VCC / GND | 3V3 / GND | — |

接线完成后把 `config.py` 里 `ENABLE_MPU6050`、`ENABLE_INA219` 改成 `True`：
- 振动点位 `vibration` = 合加速度相对 1g 的偏移，静止约 0.000，晃动明显上升；
- 电流 `current_a` / 功率 `power_w` 走 INA219 板载 0.1Ω 采样电阻（`INA219_SHUNT_OHM`）。

### 网关节点 GW-01（`ROLE = "gateway"`）

只接板载 LED，自身上报 `rssi`，同时承担两项边缘职责：
- **ESP-NOW 汇聚**：CW/TR 设 `SEND_MODE="espnow"` 并填 `GW_MAC` 后，子节点把 envelope 单播给网关，网关入队后统一走 HTTP 上行（子节点发送失败自动落本地缓存，恢复后仍走 WiFi 补传）。
- **MQTT 下行**：订阅 `iot/GW-01/cmd`，接收 `{"action":"ota","target_version":"3.1.0"}` 触发文件级 OTA（见第七节）。

要点：

- 所有器件共地，统一 3.3V 供电；ESP32 的 GPIO 不耐 5V。
- DHT22 的 DATA 与 VCC 之间需要 4.7k~10kΩ 上拉（模块板通常已内置；分立元件长导线时必加）。
- 门磁使用 **GPIO 内部上拉**，无需外接电阻：门关闭 → 磁簧吸合 → GPIO5 读到低电平 → `door=false`；开门 → 高电平 → `door=true`。
- DHT22 两次采样间隔必须 ≥ 2 秒，固件默认 10 秒。

## 三、烧录与配置

1. 用 esptool 或 Thonny 给 ESP32 刷 MicroPython（v1.22+，esp32 通用版）。
2. 把 `config.py`、`main.py`、`ota.py` 上传到板子根目录。若要用 MQTT 下行 OTA，再上传 `umqtt/simple.py`（目录结构必须是 `/umqtt/simple.py`；microPython-lib 里取 `umqtt/simple.py` 即可）。缺 `umqtt` 时固件自动降级为纯 HTTP 上报，其余功能不受影响。
   - `config.py` / `boot.py` **永不参与 OTA 分发**：节点身份、引脚、WiFi、令牌都留在本地，升级不会把网关配置刷到子节点。
   - 出厂版本号写在 `config.py` 的 `FIRMWARE_VERSION`；OTA 成功后会写 `version.txt` 覆盖读取优先级，避免 `config.py` 不参与分发导致的版本回退。

**同一份 `main.py`，只改 `config.py`**：

| 配置项 | 取值 |
|---|---|
| `ROLE` | `"cold"` / `"trans"` / `"gateway"` |
| `DEVICE_CODE` | 留空则按角色取默认：`CW-01` / `TR-01` / `GW-01`；同角色多板时手动改成 `CW-02` 等 |
| `WIFI_SSID` / `WIFI_PASSWORD` | 现场 2.4GHz WiFi（ESP32 不支持 5GHz） |
| `HTTP_BASE` | 本机开发 `http://<平台IP>:8002`；docker/nginx 部署 `http://<平台IP>:8080` |
| `DEVICE_TOKEN` | `backend/.env` 中的 `DEVICE_INGEST_TOKEN`（未配置可留空） |
| `INTERVAL` | 采样间隔，默认 10 秒 |
| `CACHE_LIMIT` | 离线缓存条数，默认 240（约 40 分钟） |
| `ENABLE_MPU6050` / `ENABLE_INA219` | 运输节点接好线后改 `True` |
| `ENABLE_MQTT` | `True` 时订阅下行指令（OTA/重启）；`umqtt` 缺失自动跳过 |
| `MQTT_HOST` / `MQTT_PORT` | 平台侧 EMQX/broker 地址，如 `192.168.1.100:1883` |
| `MQTT_USER` / `MQTT_PASSWORD` | 匿名 broker 留空 |
| `SEND_MODE` | `"wifi"`（默认，直连上行）或 `"espnow"`（汇聚到网关） |
| `GW_MAC` | `SEND_MODE="espnow"` 时必填，网关 STA MAC，如 `24:0A:C4:xx:xx:xx` |
| `OTA_VERSION_FILE` | 记录 OTA 后版本，默认 `version.txt` |
| `OTA_PUBLIC_KEY` | 清单验签公钥（Ed25519，裸 base64 或 PEM）；与 `.env` 的 `OTA_PUBLIC_KEY` 一致 |
| `OTA_ALLOW_UNSIGNED` | 仅调试用。生产置 `False`，拒绝未签名的清单 |

轮换角色时只替换 `config.py`（或改两行）再软重启，无需重新烧录固件。

3. 重启后串口 115200 应看到：

```
[CW-01] 角色 cold 就绪：dht=True door=True mpu=False ina=False
[CW-01] WiFi 已连接: 192.168.x.x
[CW-01] NTP 对时成功
[CW-01] 补传成功 4 条，剩余 0
```

4. 固件行为：
   - 每条上报含 `seq`（本地递增）、`ts`（NTP 对时后的东八区时间）、`quality`、`firmware_version`；
   - 冷库节点温度点位为 `temp_in`，运输节点为 `temp_supply`（按 `ROLE` 派生 `TEMP_POINT`）；
   - 传感器缺失或读取失败只降级（缺该点位或 `quality=stale`），不阻塞上报；
   - 未对时成功时省略 `ts`，由平台按接收时间落库，`quality` 置 `stale`，避免写入 2000 年的错误时间；
   - 断网时数据写入 `/telemetry_cache.json` 环形缓存，恢复后按 `seq` 从旧到新批量补传（50 条/批，后端上限 200）；
   - 补传遇到 4xx 视为脏数据直接丢弃，避免个别坏点堵死队列；平台侧幂等，重复重放不会产生重复行。

## 四、无硬件演练（推荐先跑通）

```powershell
# 令牌从 backend/.env 读取，本机后端端口 8002
$env:DEVICE_TOKEN='<DEVICE_INGEST_TOKEN>'
$env:API_BASE='http://127.0.0.1:8002'

# 三段合并演练：门磁开合 → 越限告警/恢复 → 断网 5 条后补传
python iot/simulator_http.py --device SIM-HTTP-01 --scenario all --interval 1

# 单独演练
python iot/simulator_http.py --device SIM-HTTP-01 --scenario door
python iot/simulator_http.py --device SIM-HTTP-01 --scenario alarm
python iot/simulator_http.py --device SIM-HTTP-01 --scenario offline

# 交互模式：o 开门 / c 关门 / h 越限 / n 恢复 / f 断网补传 / q 退出
python iot/simulator_http.py --device SIM-HTTP-01
```

预期串口输出（节选）：

```
门磁 → 开
2026-11-09T23:29:24 temp=-18.0℃ door=True → accepted=4 duplicates=0 event=door:门磁开启
2026-11-09T23:28:56 temp=-2.0℃ door=False → accepted=4 duplicates=0 event=alarm:库内温度 -2.0℃ 高于上限 -5.0℃
2026-11-09T23:28:58 temp=-18.0℃ door=False → accepted=4 duplicates=0 event=recovered:temp_in 已恢复正常区间
断网中，缓存第 5 条 ts=2026-11-09T23:29:04
网络恢复，转入批量补传
补传成功 5 条 → accepted=20 duplicates=0
```

## 五、平台侧验证

本机开发把 `8002` 换成你的后端端口；docker/nginx 部署用 `8080` 并加 `/api/v1` 前缀即可。

```bash
# 1）设备面板：点位最新值 + 数据新鲜度
curl http://127.0.0.1:8002/api/v1/iot/devices/CW-01/state

# 2）点位字典与阈值
curl http://127.0.0.1:8002/api/v1/iot/devices/CW-01/points

# 3）事件流：门磁开合、越限与恢复
curl "http://127.0.0.1:8002/api/v1/iot/devices/CW-01/events?limit=10"

# 4）活跃/历史告警
curl "http://127.0.0.1:8002/api/v1/iot/alerts?limit=10"

# 5）温度曲线（时间正序）
curl "http://127.0.0.1:8002/api/v1/iot/devices/CW-01/series?point_key=temp_in&limit=60"
```

三节点同时上电后，`/api/v1/iot/devices` 应能看到 `CW-01`、`TR-01`、`GW-01` 三台设备，状态为 `online`。
大屏与设备孪生面板走同一读模型，WebSocket 会推送 `telemetry` 与 `twin_event`，无需刷新。

## 六、三段验收演练（实机）

### 演练 A：断网补传

1. 设备正常运行，串口出现 `补传成功 … 剩余 0`。
2. 拔掉路由器网线或关闭热点，让设备离线 **约 2 分钟**（≥ 6 条采样）。
3. 串口出现 `HTTP 上报异常`，并持续打印缓存条数；平台设备状态在 90 秒后转为离线。
4. 恢复网络，串口应出现 `补传成功 N 条`，且 N 与离线期间采样数一致。
5. 平台验证：`/events` 中的历史时间戳连续，`/state` 的 `last_seen_at` 追上当前时间；重复执行同一批补传时 `duplicates` 递增而 `accepted` 为 0。

### 演练 B：门磁开合

1. 保持门关闭，确认 `/state` 中 `door=false`。
2. 打开冷库门（或保温箱盖），1~2 个采样内 `/state` 变为 `door=true`，`/events` 新增 `door_open`（severity=warn）。
3. 关门后新增 `door_close`（severity=info）。
4. 验收标准：一次开合恰好产生一条开启 + 一条关闭，不重复、不抖动。CW-01 与 TR-01 可先后各做一次，验证多设备互不干扰。

### 演练 C：越限与恢复

1. 用吹风机/暖手宝靠近 DHT22，使 `temp_in`（或 `temp_supply`）升到 -5℃ 以上。
2. 连续 3 个采样越限后触发告警：`/events` 出现 `alarm_temp_in_high`，`/alerts` 出现 `temp_in_high`（critical）。
3. 撤掉热源，温度回到 -18℃ 后：事件 `resolved_at` 被填写，告警状态变为 `resolved`。
4. 反例验证：只越限 1~2 个采样不会告警，说明去抖生效。

### 演练 D：运输振动与电流（MPU6050 / INA219 到货后）

1. 静止放置 TR-01，`/state` 的 `vibration` 应接近 0。
2. 轻晃面包板，`vibration` 明显上升；`current_a` 随负载变化（INA219 串在 USB 供电回路或外部小负载）。
3. 这一步只验证采集与上报，不做算法判定，避免一上来就陷入阈值调参。

## 七、OTA 升级（MQTT 下行 + 文件级）

服务端已闭环：`POST /api/v1/devices/ota` 建任务 → MQTT 下发 `{"action":"ota","task_id","target_version"}` → 设备拉
`GET /api/v1/devices/ota/manifest/<version>` → 逐文件 `GET /api/v1/devices/ota/file/<version>/<name>` → 设备
`POST /api/v1/devices/ota/report` 回执。设备侧执行器为 `ota.py`。

### 1. 打发布包（在仓库根目录）

```powershell
# 正式发布：私钥只放发布机/CI，公钥写入 .env 与设备 config.py
python iot/tools/make_release.py 3.1.0 --sign-key <32字节私钥hex>
# 仅内网调试可省略签名
python iot/tools/make_release.py 3.1.0
```

产物：`iot/firmware/releases/3.1.0/{manifest.json, main.py, ota.py}`。脚本自动收集 `iot/firmware/*.py`，
**强制排除 `config.py` / `boot.py` / `make_release.py`**，manifest 记录每个文件的 `size` 与 `sha256`；
带 `--sign-key` 时会写入 `signature` / `signature_alg=ed25519` / `public_key`，并打印公钥。
改了 `main.py` 或 `ota.py` 后必须重跑一次，否则发布包与源码不一致（设备会校验 sha256 并失败）。

### 2. 触发升级（管理员）

```bash
# 登录后拿 JWT，再建 OTA 任务；device_ids 省略表示全部设备
# rollout_percent < 100 时按 batch_id + 设备编码哈希确定抽样（灰度），至少 1 台
curl -X POST http://127.0.0.1:8002/api/v1/devices/ota \
  -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" \
  -d '{"target_version":"3.1.0","device_ids":[1,2,3],"rollout_percent":10}'

# 观察批次无失败后续发全量；异常时整批回滚
curl -X POST http://127.0.0.1:8002/api/v1/devices/ota/batch/<batch_id>/promote \
  -H "Authorization: Bearer <JWT>"
curl -X POST http://127.0.0.1:8002/api/v1/devices/ota/batch/<batch_id>/rollback \
  -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" -d '{}'
```

设备需满足：`ENABLE_MQTT=True`、`MQTT_HOST/PORT` 已配、已上传 `umqtt/simple.py`、且固件已在运行（订阅 `iot/<code>/cmd`）。

### 3. 设备侧串口预期

```
[GW-01] MQTT 已连接，订阅 iot/GW-01/cmd
[GW-01] 收到下行指令: ota {'task_id': 7, 'target_version': '3.1.0'}
[GW-01] OTA 3.1.0: main.py (7231B) 校验通过
[GW-01] OTA 3.1.0: ota.py (5980B) 校验通过
[GW-01] OTA 3.1.0 完成，写入 version.txt 并重启
```

重启后 `current_version()` 读到 `version.txt`，上报的 `firmware_version` 随之为 `3.1.0`。

### 4. 平台侧复核

```bash
# 任务状态与回执
curl "http://127.0.0.1:8002/api/v1/devices/ota" -H "Authorization: Bearer <JWT>"
# 设备详情里的 firmware_version 应更新
curl http://127.0.0.1:8002/api/v1/iot/devices/CW-01/state
```

### 5. 安全边界

- 版本号白名单 `^[0-9A-Za-z][0-9A-Za-z._-]{0,19}$`，文件名白名单 `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.py$`；
- **清单 Ed25519 验签**：设备下载前用 `config.py` 的 `OTA_PUBLIC_KEY` 校验签名，签名不匹配直接中止；
  `OTA_ALLOW_UNSIGNED=False` 时未签名清单一律拒绝（服务端同样校验，防止中间人篡改版本/哈希）；
- 服务端与设备端**双重剔除** `config.py` / `boot.py`，防止把网关配置推到子节点；
- 解析后的父目录必须等于版本目录，阻止路径穿越；
- 设备先写 `name.new` 再改名，单个文件下载/校验失败即中止并上报 `failed`，保留旧固件可继续运行；
- 回执 `message` 截断 200 字符，失败原因可在任务列表里直接看到。

## 八、常见问题

| 现象 | 排查 |
|---|---|
| 上报返回 401 | `DEVICE_TOKEN` 与 `backend/.env` 的 `DEVICE_INGEST_TOKEN` 不一致 |
| 上报返回 400 | 点位键不在字典中，或取值无法按 number/bool 解析；看响应 `detail` |
| 平台一直离线 | `DEVICE_CODE` 大小写/空格不一致；确认设备能访问 `HTTP_BASE`（手机热点同网段测试） |
| 两台设备显示同一编码 | `config.py` 里 `DEVICE_CODE` 留空导致同角色取到默认值，同角色多板要手动区分 |
| WiFi 连不上 | ESP32 只支持 2.4GHz；检查 SSID/密码与路由器白名单 |
| 温度正常但告警不停 | 检查 `DevicePoint` 上的阈值是否被资源级规则覆盖 |
| 时间戳错乱 | 设备未对时成功，确认 `ntptime` 可用；或让平台按接收时间落库（省略 ts） |
| 缓存文件写失败 | 闪存满或文件损坏；删除 `telemetry_cache.json` 后重启，平台幂等不受影响 |
| 补传后 `duplicates` 偏多 | 平台时间精度为秒，采样间隔应 ≥ 1 秒；同一秒的同点位数据会被幂等去重 |
| 读数恒为 0 / 报错 | DHT22 采样间隔 ≥ 2 秒；检查上拉电阻与 3.3V 供电 |
| MPU6050/INA219 无点位 | 先确认 `ENABLE_*` 为 `True`；再检查 I2C 是否识别（`i2c.scan()` 应看到 0x68 / 0x40） |
| 网关节点没有温湿度 | 正常：`gateway` 角色只上报 `rssi`，传感器点位由后续 ESP-NOW 子节点贡献 |

## 九、多设备接入

同一固件改 `config.py` 的 `ROLE` 与 `DEVICE_CODE` 后刷到对应板子即可；设备首次上报会自动建档
（`resource_id=0`），再到「设备管理」绑定到对应冷库/箱位/车辆，或在设备孪生面板按空间批量绑定。

## 十、后续演进

| 阶段 | 内容 | 状态 |
|---|---|---|
| H1 准备 | 物料到位、MicroPython 刷机、单节点直连上报 | 已完成 |
| H2 三节点直连 | CW-01 / TR-01 / GW-01 同固件靠 `ROLE` 切换，HTTP 窄表上报 | 已完成 |
| H3 ESP-NOW 汇聚 | 子节点 `SEND_MODE="espnow"` 单播到网关，网关统一上行，失败回落本地缓存 | 已实现，待实机验证 |
| H4 MQTT 下行 + 文件级 OTA | 订阅 `iot/<code>/cmd`，按 manifest 校验 sha256 覆盖 `.py` 后重启 | 已实现，待实机验证 |
| H5 LoRa 远距离回传 | 替换 WiFi 做港区级覆盖验证 | 待二期，需增补 SX1278 |

本期验收口径：三节点上电即可跑通「组网 + 补传 + 门磁 + 越限」四段演练，OTA 在 PC 侧 `pytest` 与
`iot/simulator_http.py` 之外，建议至少实机升级一块板子（推荐网关）验证串口与 `version.txt` 回写。
