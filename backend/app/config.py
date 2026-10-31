"""全局配置：从环境变量 / .env 读取。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "怀化国际陆港物流资源共享与智能撮合平台"

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

    # 告警阈值默认值（可被 alert_rules 表中的全局/单资源规则覆盖）
    alert_temp_min: float = -30.0
    alert_temp_max: float = -5.0
    alert_humidity_max: float = 90.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
