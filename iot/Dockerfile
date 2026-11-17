FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

WORKDIR /app

COPY iot/simulator_http.py ./

# 演示默认设备走 HTTP 窄表上报；交互命令需 docker run -it
CMD ["python", "simulator_http.py", "--device", "SIM-DEMO-01", "--interval", "5"]
