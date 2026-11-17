"""ESP32 冷链采集节点（MicroPython）—— 角色化固件。

角色由 config.py 的 ROLE 决定，同一份 main.py 适配三类节点：
  cold     冷库节点  DHT22 + 门磁
  trans    运输节点  DHT22 + 门磁（可选 MPU6050 振动 / INA219 电流）
  gateway  网关节点  直连平台 + ESP-NOW 汇聚子节点数据

链路：HTTP 窄表上报 POST /api/v1/iot/telemetry
- 每 INTERVAL 秒采集一次：温度、湿度、门磁、rssi
- 断网时写入板载环形缓存（默认 240 条，约 40 分钟），恢复后按 seq 顺序批量补传
- 平台按 (设备, 点位, 时间戳) 幂等去重，补传可安全重放
- 上电后尝试 NTP 对时；未对时成功时省略 ts，由平台按接收时间落库（quality 标记 stale）

OTA：MQTT 订阅 iot/<device_code>/cmd，收到 {"action":"ota","target_version":"x.y.z"}
后交给 ota.py 拉清单、校验、覆盖 .py（不含 config.py）并重启。

烧录前只需修改 config.py。
依赖：MicroPython v1.22+（esp32 通用版），dht / network / urequests 为固件内置；
      MQTT 需额外上传 umqtt/simple.py，缺失时自动降级为纯 HTTP 上报。
"""

import json
import time

import network
from machine import Pin

import config as cfg

try:
    import urequests
except ImportError:  # 极简固件可能未内置，需自行上传 urequests.py
    urequests = None

try:
    from umqtt.simple import MQTTClient
except ImportError:  # 未上传 umqtt 时降级为纯 HTTP，不影响采集
    MQTTClient = None

led = Pin(cfg.LED_PIN, Pin.OUT)
wlan = network.WLAN(network.STA_IF)

dht_sensor = None
door_sensor = None
i2c = None
mpu_ready = False
ina_ready = False

mqtt = None
_mqtt_last_try = 0
espnow = None
espnow_peer = None

clock_synced = False
seq = 0
queue = []


def log(*args):
    if cfg.DEBUG:
        print("[%s]" % cfg.DEVICE_CODE, *args)


def current_version():
    """OTA 成功后 version.txt 记录新版本；未升级过则用 config 里的出厂版本。"""
    try:
        with open(cfg.OTA_VERSION_FILE) as f:
            version = f.read().strip()
        return version or cfg.FIRMWARE_VERSION
    except OSError:
        return cfg.FIRMWARE_VERSION


# ---------------- 传感器初始化 ----------------

def init_sensors():
    """按角色初始化传感器；缺传感器只降级，不阻塞上报。"""
    global dht_sensor, door_sensor, i2c, mpu_ready, ina_ready

    if cfg.ROLE in ("cold", "trans"):
        try:
            import dht
            dht_sensor = dht.DHT22(Pin(cfg.DHT_PIN))
        except Exception as e:
            log("DHT22 初始化失败:", e)
        door_sensor = Pin(cfg.DOOR_PIN, Pin.IN, Pin.PULL_UP)

    if cfg.ENABLE_MPU6050 or cfg.ENABLE_INA219:
        try:
            from machine import I2C
            i2c = I2C(0, scl=Pin(cfg.I2C_SCL), sda=Pin(cfg.I2C_SDA), freq=400000)
        except Exception as e:
            log("I2C 初始化失败:", e)

    if cfg.ENABLE_MPU6050 and i2c is not None:
        try:
            i2c.writeto_mem(cfg.MPU6050_ADDR, 0x6B, b"\x00")  # 解除休眠
            mpu_ready = True
        except Exception as e:
            log("MPU6050 初始化失败:", e)

    if cfg.ENABLE_INA219 and i2c is not None:
        try:
            i2c.writeto_mem(cfg.INA219_ADDR, 0x00, b"\x39\x9f")  # 32V/2A 连续采样
            ina_ready = True
        except Exception as e:
            log("INA219 初始化失败:", e)

    log(
        "角色 %s 就绪：dht=%s door=%s mpu=%s ina=%s"
        % (cfg.ROLE, dht_sensor is not None, door_sensor is not None, mpu_ready, ina_ready)
    )


# ---------------- 缓存（断电不丢） ----------------

def load_cache():
    global seq
    try:
        with open(cfg.CACHE_FILE) as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("seq"), int):
            seq = max(seq, item["seq"])
    log("载入未上报缓存", len(data), "条")
    return data


def save_cache():
    try:
        with open(cfg.CACHE_FILE, "w") as f:
            json.dump(queue[-cfg.CACHE_LIMIT:], f)
    except Exception as e:
        log("缓存写入失败:", e)


def enqueue(envelope):
    queue.append(envelope)
    if len(queue) > cfg.CACHE_LIMIT:
        del queue[: len(queue) - cfg.CACHE_LIMIT]
    save_cache()


# ---------------- 网络与时钟 ----------------

def wifi_connect(timeout=20):
    wlan.active(True)
    if wlan.isconnected():
        return True
    log("连接 WiFi:", cfg.WIFI_SSID)
    try:
        wlan.connect(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)
    except Exception as e:
        log("WiFi 发起连接失败:", e)
        return False
    for _ in range(timeout * 2):
        if wlan.isconnected():
            log("WiFi 已连接:", wlan.ifconfig()[0])
            return True
        time.sleep(0.5)
    log("WiFi 连接超时")
    return False


def sync_clock():
    """NTP 对时；失败则后续上报省略 ts，由平台补时间。"""
    global clock_synced
    try:
        import ntptime
        ntptime.settime()
        clock_synced = True
        log("NTP 对时成功")
        return True
    except Exception as e:
        clock_synced = False
        log("NTP 对时失败（将省略 ts）:", e)
        return False


def now_iso():
    if not clock_synced:
        return None
    t = time.localtime(time.time() + cfg.TZ_OFFSET)
    return "%04d-%02d-%02dT%02d:%02d:%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])


# ---------------- MQTT 下行（OTA 指令） ----------------

def on_mqtt_message(topic, msg):
    """平台下发指令：{"action":"ota","task_id":1,"target_version":"3.1.0"}。"""
    try:
        payload = json.loads(msg)
    except Exception:
        log("收到非 JSON 指令:", msg)
        return
    if not isinstance(payload, dict):
        return
    action = payload.get("action")
    log("收到下行指令:", action, payload)
    if action == "ota":
        try:
            import ota
        except ImportError as e:
            log("缺少 ota.py，无法升级:", e)
            return
        ota.perform(payload.get("target_version", ""))
    elif action == "reboot":
        import machine
        machine.reset()


def mqtt_connect():
    global mqtt
    if not cfg.ENABLE_MQTT:
        return False
    if MQTTClient is None:
        log("缺少 umqtt.simple，跳过 MQTT（仅 HTTP 上报）")
        return False
    client_id = cfg.MQTT_CLIENT_ID or ("hhlg-" + cfg.DEVICE_CODE)
    try:
        client = MQTTClient(
            client_id, cfg.MQTT_HOST, cfg.MQTT_PORT,
            cfg.MQTT_USER or None, cfg.MQTT_PASSWORD or None,
            keepalive=cfg.MQTT_KEEPALIVE,
        )
        client.set_callback(on_mqtt_message)
        client.connect()
        topic = "iot/%s/cmd" % cfg.DEVICE_CODE
        client.subscribe(topic)
        mqtt = client
        log("MQTT 已连接，订阅", topic)
        return True
    except Exception as e:
        log("MQTT 连接失败:", e)
        mqtt = None
        return False


def mqtt_poll():
    """每次主循环调用；断线后每 30 秒重连一次，不阻塞采集。"""
    global mqtt, _mqtt_last_try
    if not cfg.ENABLE_MQTT or MQTTClient is None:
        return
    if mqtt is None:
        now = time.time()
        if now - _mqtt_last_try >= 30:
            _mqtt_last_try = now
            mqtt_connect()
        return
    try:
        mqtt.check_msg()
    except Exception as e:
        log("MQTT 连接异常，稍后重连:", e)
        try:
            mqtt.disconnect()
        except Exception:
            pass
        mqtt = None


# ---------------- ESP-NOW 汇聚（可选组网方式） ----------------

def init_espnow():
    """网关监听子节点；子节点把 envelope 单播给网关（两端需同一 WiFi 信道）。"""
    global espnow, espnow_peer
    try:
        import espnow as espnow_mod
    except ImportError:
        log("固件不含 espnow 模块，SEND_MODE=espnow 不可用")
        return False
    try:
        link = espnow_mod.ESPNow()
        link.active(True)
    except Exception as e:
        log("ESP-NOW 初始化失败:", e)
        return False

    if cfg.ROLE == "gateway":
        espnow = link
        log("ESP-NOW 网关就绪，等待子节点汇聚")
        return True

    if not cfg.GW_MAC:
        log("未配置 GW_MAC，ESP-NOW 不可用")
        return False
    try:
        peer = bytes(int(x, 16) for x in cfg.GW_MAC.split(":"))
        link.add_peer(peer)
    except Exception as e:
        log("添加网关 MAC 失败:", e)
        return False
    espnow = link
    espnow_peer = peer
    log("ESP-NOW 子节点就绪 →", cfg.GW_MAC)
    return True


def espnow_send(envelope):
    """子节点发送；失败返回 False，由调用方落本地缓存走 WiFi 补传。"""
    if espnow is None or espnow_peer is None:
        return False
    try:
        espnow.send(espnow_peer, json.dumps(envelope))
        return True
    except Exception as e:
        log("ESP-NOW 发送失败:", e)
        return False


def espnow_drain():
    """网关：把收到的子节点 envelope 放入待转发队列，返回本次接收条数。"""
    if espnow is None:
        return 0
    count = 0
    while True:
        try:
            msg = espnow.recv(0)
        except TypeError:
            try:
                msg = espnow.recv(timeout=0)
            except Exception:
                return count
        except Exception as e:
            log("ESP-NOW 接收异常:", e)
            return count
        if not msg:
            return count
        try:
            envelope = json.loads(msg[1])
        except Exception:
            continue
        if isinstance(envelope, dict) and envelope.get("device_code"):
            enqueue(envelope)
            count += 1
            log("汇聚", envelope["device_code"], "seq", envelope.get("seq"))
    return count


# ---------------- 采集 ----------------

def read_door():
    """上拉接法：门关闭（磁簧吸合）为低电平，门开为高电平。"""
    return door_sensor.value() == 1


def read_climate():
    try:
        dht_sensor.measure()
        return round(dht_sensor.temperature(), 1), round(dht_sensor.humidity(), 1)
    except Exception as e:
        log("DHT22 读取失败:", e)
        return None


def signal_strength():
    try:
        rssi = wlan.status("rssi")
        return int(rssi) if isinstance(rssi, (int, float)) else None
    except Exception:
        return None


def _s16(hi, lo):
    v = (hi << 8) | lo
    return v - 65536 if v >= 32768 else v


def read_vibration():
    """MPU6050：合加速度相对 1g 的偏移（g），静止约 0.000。"""
    buf = i2c.readfrom_mem(cfg.MPU6050_ADDR, 0x3B, 6)
    ax = _s16(buf[0], buf[1]) / 16384.0
    ay = _s16(buf[2], buf[3]) / 16384.0
    az = _s16(buf[4], buf[5]) / 16384.0
    total = (ax * ax + ay * ay + az * az) ** 0.5
    return round(abs(total - 1.0), 3)


def read_power():
    """INA219：返回 (电流 A, 功率 W)。母线 LSB 4mV，分流 LSB 10uV。"""
    bus = i2c.readfrom_mem(cfg.INA219_ADDR, 0x02, 2)
    bus_v = ((((bus[0] << 8) | bus[1]) >> 3) & 0x1FFF) * 0.004
    sh = i2c.readfrom_mem(cfg.INA219_ADDR, 0x01, 2)
    shunt_mv = _s16(sh[0], sh[1]) * 0.01
    current = shunt_mv / 1000.0 / cfg.INA219_SHUNT_OHM
    return round(current, 2), round(bus_v * current, 1)


def collect():
    """组装一条 TelemetryEnvelope；传感器缺失或读失败只降级，不中断上报。"""
    global seq
    points = {}
    quality = "good"

    if door_sensor is not None:
        points["door"] = read_door()

    if dht_sensor is not None:
        climate = read_climate()
        if climate is None:
            quality = "stale"
        else:
            points[cfg.TEMP_POINT] = climate[0]
            points["hum_in"] = climate[1]

    if mpu_ready:
        try:
            points["vibration"] = read_vibration()
        except Exception as e:
            log("MPU6050 读取失败:", e)

    if ina_ready:
        try:
            points["current_a"], points["power_w"] = read_power()
        except Exception as e:
            log("INA219 读取失败:", e)

    rssi = signal_strength()
    if rssi is not None:
        points["rssi"] = rssi

    envelope = {
        "device_code": cfg.DEVICE_CODE,
        "seq": seq,
        "quality": quality,
        "firmware_version": current_version(),
        "points": points,
    }
    ts = now_iso()
    if ts is not None:
        envelope["ts"] = ts
    seq += 1
    return envelope


# ---------------- 上报与补传 ----------------

def post_batch(items):
    """返回 HTTP 状态码；网络异常返回 None。"""
    if urequests is None:
        log("urequests 不可用，无法上报")
        return None
    headers = {"Content-Type": "application/json"}
    if cfg.DEVICE_TOKEN:
        headers["X-Device-Token"] = cfg.DEVICE_TOKEN
    body = json.dumps({"items": items})
    try:
        resp = urequests.post(
            cfg.HTTP_BASE + "/api/v1/iot/telemetry", data=body, headers=headers
        )
        code = resp.status_code
        try:
            resp.close()
        except Exception:
            pass
        return code
    except Exception as e:
        log("HTTP 上报异常:", e)
        return None


def flush_queue():
    """从最旧开始按序补传；成功一批删一批，4xx 视为脏数据直接丢弃，避免堵死队列。"""
    while queue:
        batch = queue[: cfg.BATCH_SIZE]
        code = post_batch(batch)
        if code in (200, 201):
            del queue[: len(batch)]
            save_cache()
            log("补传成功", len(batch), "条，剩余", len(queue))
            continue
        if code is not None and 400 <= code < 500:
            log("批次被拒（", code, "），丢弃", len(batch), "条")
            del queue[: len(batch)]
            save_cache()
            continue
        return False
    return True


def idle(seconds):
    """分片等待：每秒轮询一次 MQTT，保证 OTA 指令秒级响应。"""
    end = time.time() + seconds
    while time.time() < end:
        mqtt_poll()
        time.sleep(1)


def connect_all():
    """WiFi + NTP；MQTT 由 mqtt_poll 按 30 秒节流重连，避免频繁拨号。"""
    if not wlan.isconnected():
        if not wifi_connect():
            return False
        sync_clock()
    return True


def gateway_loop():
    """网关：ESP-NOW 收子节点数据 → 入队 → 统一 HTTP 转发；同时上报自身 rssi 心跳。"""
    next_heartbeat = time.time()
    while True:
        espnow_drain()
        connect_all()
        drained = flush_queue() if wlan.isconnected() else False
        led.value(1 if drained else 0)
        mqtt_poll()

        now = time.time()
        if now >= next_heartbeat:
            next_heartbeat = now + cfg.INTERVAL
            enqueue(collect())
        time.sleep(1)


def node_loop():
    """子节点：采集 → ESP-NOW 发给网关（失败落本地缓存）→ WiFi 补传。"""
    while True:
        connect_all()
        envelope = collect()
        if cfg.SEND_MODE == "espnow" and espnow_send(envelope):
            log("已发送至网关 seq", envelope["seq"])
        else:
            enqueue(envelope)

        drained = flush_queue() if wlan.isconnected() else False
        led.value(1 if drained else 0)
        idle(cfg.INTERVAL)


def main():
    global queue
    if urequests is None:
        log("警告：固件缺少 urequests，无法 HTTP 上报")

    init_sensors()
    if cfg.SEND_MODE == "espnow":
        init_espnow()

    while not wifi_connect():
        led.value(0)
        time.sleep(5)
    sync_clock()
    mqtt_connect()

    queue = load_cache()

    if cfg.ROLE == "gateway":
        log("网关模式：ESP-NOW 汇聚 + 统一转发平台")
        gateway_loop()
    else:
        log("采集模式：SEND_MODE =", cfg.SEND_MODE)
        node_loop()


if __name__ == "__main__":
    main()
