FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

WORKDIR /app

RUN pip install --no-cache-dir "paho-mqtt>=2.0,<3.0"

COPY iot/simulator.py ./
COPY iot/simulator_http.py ./

# 演示默认走 MQTT 直采（同时写 iot_data 与窄表 telemetry）；HTTP 窄表脚本保留供手工联调
CMD ["python", "simulator.py"]
