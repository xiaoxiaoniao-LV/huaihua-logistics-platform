"""全局配置：从环境变量 / .env 读取。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 代码仓根目录（backend/app/config.py → 仓库根）
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "怀化国际陆港冷链资源智能撮合平台"

    database_url: str = (
        "mysql+pymysql://logistics:logistics123@localhost:3306/"
        "huaihua_logistics?charset=utf8mb4"
    )
    redis_url: str = "redis://localhost:6379/0"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # 佣金费率（平台抽成比例，0.0 ~ 1.0），订单 finished 时结算
    commission_rate: float = 0.10

    jwt_secret: str = "please-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 默认 24 小时
    refresh_token_expire_minutes: int = 10080  # 刷新令牌有效期，默认 7 天

    # 登录失败限流：同一用户名连续失败超过阈值则锁定一段时间（防暴力破解）
    login_max_attempts: int = 5
    login_lock_seconds: int = 900  # 锁定 15 分钟

    # 允许跨域的前端源，逗号分隔；生产环境请改成实际域名
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 设备 HTTP 上报令牌（X-Device-Token）；留空表示不校验（仅限本地开发）
    device_ingest_token: str = ""

    # 设备超过该秒数未上报即判定为离线
    device_offline_seconds: int = 90

    # 固件仓库目录：存放 releases/<version>/{manifest.json, *.py}，供设备文件级 OTA 拉取
    # 本地默认指向仓库内 iot/firmware/releases；Docker 中由 FW_REPO_DIR=/app/fw/releases 覆盖
    fw_repo_dir: str = str(_REPO_ROOT / "iot" / "firmware" / "releases")

    # 固件清单签名：私钥不进入运行环境，只由打包工具离线使用；后端只做验签。
    # 公钥格式为裸 base64 的 32 字节 Ed25519 公钥；配置后清单必须带有效签名
    ota_public_key: str = ""
    # 未配置公钥时是否仍允许下发未签名清单（生产必须为 True，仅内网调试可显式关闭）
    ota_require_signature: bool = True

    # 结算凭证（发票 PDF）抬头：销售方为平台运营主体，税率用于单据上的税额估算
    invoice_seller_name: str = "怀化国际陆港冷链资源智能撮合平台"
    invoice_seller_tax_no: str = ""
    invoice_tax_rate: float = 0.06

    # 告警阈值默认值（可被 alert_rules 表中的全局/单资源规则覆盖）
    alert_temp_min: float = -30.0
    alert_temp_max: float = -5.0
    alert_humidity_max: float = 90.0

    # 支付：sandbox=本机模拟支付（不联网）；off=仅线下合同
    payment_mode: str = "sandbox"
    alipay_app_id: str = ""
    alipay_gateway: str = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    # 支付宝公钥（PEM 或后台拷贝的裸 base64），配置后异步通知强制 RSA2 验签
    alipay_public_key: str = ""
    # 可选：校验通知中的 seller_id（支付宝商户号），留空表示不校验
    alipay_seller_id: str = ""
    # /metrics 抓取令牌，留空表示不鉴权（仅建议内网暴露）
    metrics_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
