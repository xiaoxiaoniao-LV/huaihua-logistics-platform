"""节点配置：烧录前只改这个文件，main.py 不用动。

ROLE 决定节点角色与上报点位（同一份固件适配三类节点）：
  cold     冷库节点  CW-01  temp_in      + 湿度 + 门磁 + rssi
  trans    运输节点  TR-01  temp_supply  + 湿度 + 门磁 + rssi（可选振动/电流）
  gateway  网关节点  GW-01  仅 rssi；后续承接 ESP-NOW 汇聚与 MQTT 下行 OTA

多块同角色节点时，手动改 DEVICE_CODE 区分即可。
"""

# ==================== 节点角色 ====================
ROLE = "cold"                  # cold / trans / gateway
DEVICE_CODE = ""               # 留空则按 ROLE 取默认编码
DEBUG = True

# ==================== WiFi 与平台 ====================
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"

# 本机开发后端为 8002；docker/nginx 部署改为 http://<平台IP>:8080
HTTP_BASE = "http://192.168.1.100:8002"
DEVICE_TOKEN = "改成 backend/.env 中的 DEVICE_INGEST_TOKEN"
FIRMWARE_VERSION = "3.0.0"

# ==================== 采样与引脚 ====================
INTERVAL = 10                  # 采样/上报间隔（秒），DHT22 需 >= 2 秒
DHT_PIN = 4                    # DHT22 DATA
DOOR_PIN = 5                   # 门磁：一端 GPIO5，一端 GND（内部上拉）
LED_PIN = 2                    # 板载 LED：常亮=在线且队列清空，灭=离线或有积压

CACHE_FILE = "telemetry_cache.json"
CACHE_LIMIT = 240              # 环形缓存条数，超出丢弃最旧
BATCH_SIZE = 50                # 单次补传条数（后端上限 200）
TZ_OFFSET = 8 * 3600           # 东八区

# ==================== 可选传感器（到货接线后再打开） ====================
# 仅运输节点用得上；未接线保持 False，固件自动跳过对应点位
I2C_SDA = 21
I2C_SCL = 22
ENABLE_MPU6050 = False         # 振动 vibration
MPU6050_ADDR = 0x68
ENABLE_INA219 = False          # 电流 current_a / 功率 power_w
INA219_ADDR = 0x40
INA219_SHUNT_OHM = 0.1         # 模块板载默认 0.1Ω

# ==================== MQTT 下行（平台下发 OTA 指令） ====================
# 与 HTTP_BASE 指向同一台平台主机；docker 部署时端口用 HHLG_MQTT_PORT（默认 1884）
# 依赖板子上传 umqtt/simple.py；缺失时自动降级为纯 HTTP 上报，不影响采集
ENABLE_MQTT = True
MQTT_HOST = "192.168.1.100"
MQTT_PORT = 1883
MQTT_CLIENT_ID = ""            # 留空按 DEVICE_CODE 生成
MQTT_USER = ""
MQTT_PASSWORD = ""
MQTT_KEEPALIVE = 60

# ==================== 文件级 OTA ====================
OTA_VERSION_FILE = "version.txt"   # 升级成功后写入目标版本，重启后按此上报
OTA_TIMEOUT = 15                   # 单个 HTTP 请求超时（秒）

# ==================== 组网方式（可选 ESP-NOW 汇聚） ====================
# wifi   ：节点直连平台（默认，最稳妥）
# espnow ：子节点把数据发给网关，由网关统一 HTTP 转发（网关固定走 wifi）
SEND_MODE = "wifi"
GW_MAC = ""                    # 网关 MAC，如 "24:0a:c4:12:34:56"，SEND_MODE="espnow" 时必填

# ==================== 派生配置（一般不用改） ====================
_ROLE_DEFAULTS = {
    "cold": {"device_code": "CW-01", "temp_point": "temp_in"},
    "trans": {"device_code": "TR-01", "temp_point": "temp_supply"},
    "gateway": {"device_code": "GW-01", "temp_point": "temp_in"},
}

if ROLE not in _ROLE_DEFAULTS:
    raise ValueError("ROLE 只能是 cold / trans / gateway")

_role = _ROLE_DEFAULTS[ROLE]
if not DEVICE_CODE:
    DEVICE_CODE = _role["device_code"]
TEMP_POINT = _role["temp_point"]

# 网关必须直连平台；子节点选 espnow 时必须知道网关 MAC
if ROLE == "gateway":
    SEND_MODE = "wifi"
if SEND_MODE not in ("wifi", "espnow"):
    raise ValueError("SEND_MODE 只能是 wifi / espnow")
if SEND_MODE == "espnow" and not GW_MAC:
    raise ValueError("SEND_MODE=espnow 时必须填写 GW_MAC")
