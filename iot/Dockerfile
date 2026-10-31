FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

WORKDIR /app

RUN pip install --no-cache-dir paho-mqtt==2.1.0

COPY iot/simulator.py ./

CMD ["python", "simulator.py"]
