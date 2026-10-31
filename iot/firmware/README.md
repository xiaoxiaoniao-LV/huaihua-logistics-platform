# 实机接入：ESP32 + DHT22

无硬件时用 `iot/simulator.py` 或 docker compose 的 `simulator` 服务即可；接实机时按下面的步骤操作。

## 一、物料

| 物料 | 说明 |
|---|---|
| ESP32 开发板 | 任意带 WiFi 的 ESP32（DevKit V1 即可） |
| DHT22 / AM2302 | 温湿度传感器，冷链箱内测得范围 -40~80℃ |
| 杜邦线 / 面包板 | 3.3V 供电 |
| （可选）NEO-6M GPS | 车载场景上报经纬度 |

## 二、接线

| DHT22 | ESP32 |
|---|---|
| VCC（1 脚） | 3V3 |
| DATA（2 脚） | GPIO4（对应固件 `DHT_PIN`） |
| GND（4 脚） | GND |

> DHT22 的 DATA 与 VCC 之间建议加 4.7k~10kΩ 上拉电阻，长导线时更稳定。

## 三、烧录

1. 用 Thonny 或 `esptool` 给 ESP32 刷 MicroPython 固件（v1.22+，esp32 通用版）。
2. 修改 `main.py` 顶部「用户配置」：
   - `WIFI_SSID` / `WIFI_PASSWORD`
   - `MQTT_HOST`：运行平台的电脑局域网 IP（`ipconfig` 查看）
   - `MQTT_PORT`：docker-compose 默认映射 `1884`
   - `HTTP_BASE`：`http://<平台IP>:8080`（MQTT 不通时的降级通道）
   - `DEVICE_TOKEN`：根目录 `.env` 中的 `DEVICE_INGEST_TOKEN`
   - `DEVICE_CODE`：与平台「设备管理」页新增设备的编码 **完全一致**（如 `CW-01`）
3. 把 `main.py` 上传到板子根目录并重启（Thonny：文件 → 保存到 MicroPython 设备）。

## 四、平台侧准备

```bash
# 1）登录后注册设备（device_code 必须与固件一致）
curl -X POST http://127.0.0.1:8080/api/devices \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"device_code":"CW-01","device_type":"dht22","resource_id":1}'

# 2）确认设备在线（约 10 秒后）
curl "http://127.0.0.1:8080/api/devices?resource_id=1"

# 3）查看最新遥测
curl "http://127.0.0.1:8080/api/iot/data?device_code=CW-01&limit=5"
```

浏览器打开 `http://<平台IP>:8080`，大屏「IoT 实时监测」出现 `CW-01` 曲线即接入成功；
若温度越过阈值（默认 -30~-5℃、湿度 >90%），「活跃告警」会立即出现新记录。

## 五、验证清单

- [ ] 串口（115200）能看到 `WiFi 已连接` 与 `MQTT → iot/CW-01/data`
- [ ] 平台设备列表该设备状态为「在线」
- [ ] 拔掉传感器：串口打印「传感器读取失败」，平台 90 秒后置为「离线」
- [ ] 用吹风机加热传感器至 0℃ 以上：温度偏高告警出现
- [ ] 断电重启：设备自动重连，无需人工干预

## 六、常见问题

| 现象 | 排查 |
|---|---|
| WiFi 连不上 | ESP32 只支持 2.4GHz；检查 SSID/密码 |
| MQTT 连接失败 | 确认 `MQTT_HOST:1884` 可访问（主机防火墙放行 1884） |
| 平台一直「离线」 | `device_code` 大小写/空格不一致；EMQX 控制台 18084 看是否有该 topic |
| 读数恒为 0 / 报错 | DHT22 需 2 秒以上采样间隔；检查上拉电阻与供电 |
| 想看 MQTT 原始报文 | EMQX 控制台 → 监控 → 主题订阅 `iot/+/data` |

## 七、多设备接入

同一固件改 `DEVICE_CODE` 后刷到多块板子即可；平台侧用「自动绑定」把未绑定设备按顺序绑定到可用冷链箱，
或在「设备管理」页逐台选择绑定资源。
